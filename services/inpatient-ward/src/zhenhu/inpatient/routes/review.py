"""医生审核恢复端点 —— 接收医生审核决策，续跑 graph 主链路。

POST /inpatient/review/{patient_id}
classic: state_store → 设 *_status → plan_turn 重喂全量 state 续跑
stateful: graph.ainvoke(Command(resume=decision), config) (Phase-2 占位)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from ..agent.config import get_graph_mode
from .route_schemas import ReviewRequest

router = APIRouter(prefix="/inpatient", tags=["review"])


@router.post("/review/{patient_id}")
async def submit_review(patient_id: str, body: ReviewRequest, request: Request = None):
    """提交医生审核决策。

    review_type: doctor_confirm | med_confirm | discharge_sign
    decision: approved | rejected
    comment: 可选审核备注
    """
    from .state_store import get_state, set_state
    from ..agent.loop import get_patient_loop, get_patient_lock, resolve_pending_state

    graph_mode = get_graph_mode()

    review_type = body.review_type
    decision = body.decision
    valid_decisions = {
        "doctor_confirm": {"approved", "rejected"},
        "med_confirm": {"approved", "rejected"},
        "discharge_sign": {"approved", "rejected", "signed"},
    }
    if review_type in valid_decisions and decision not in valid_decisions[review_type]:
        return UnifiedResponse(
            error={
                "code": "INVALID_REVIEW_DECISION",
                "message": f"Decision '{decision}' is not valid for '{review_type}'",
            }
        )

    if graph_mode == "stateful":
        return UnifiedResponse(error={
            "code": "STATEFUL_GRAPH_MODE_UNAVAILABLE",
            "message": (
                "GRAPH_MODE=stateful cannot safely resume clinical reviews yet; "
                "use GRAPH_MODE=classic."
            ),
        })
    else:
        # ── O6: 持锁包裹 get_state → 修改 → plan_turn → set_state ──
        lock = get_patient_lock(patient_id)
        async with lock:
            # classic 模式：从 state_store 取状态，设置 *_status，续跑 graph
            state = get_state(patient_id)
            if not state:
                return UnifiedResponse(
                    data={"error": f"未找到患者状态: {patient_id}"},
                    error={"code": "NOT_FOUND"},
                )
            if body.expected_version is not None and body.expected_version != state.get("state_version", 0):
                from ..services.api_contract import state_version_conflict_response
                return state_version_conflict_response(
                    state.get("state_version", 0),
                    getattr(request.state, "request_id", None) if request is not None else None,
                )

            pending_review = state.get("pending_review")
            pending_type = pending_review.get("type") if isinstance(pending_review, dict) else None
            if pending_type and review_type != pending_type:
                return UnifiedResponse(error={
                    "code": "REVIEW_TYPE_MISMATCH",
                    "message": f"Patient is pending '{pending_type}', not '{review_type}'.",
                })

            # 根据 review_type 设置对应的状态字段
            if review_type == "doctor_confirm":
                # ── P1a: 合并医生编辑 ──
                if body.edits:
                    edits = body.edits

                    # 编辑 hpi_narrative
                    if edits.hpi_narrative is not None:
                        state["hpi_narrative"] = edits.hpi_narrative
                        if state.get("history_data"):
                            state["history_data"]["hpi_narrative"] = edits.hpi_narrative

                    # 编辑 pe_narrative
                    if edits.pe_narrative is not None:
                        state["pe_narrative"] = edits.pe_narrative
                        if state.get("pe_data"):
                            state["pe_data"]["pe_narrative"] = edits.pe_narrative

                    # 编辑主诉
                    if edits.chief_complaint is not None:
                        if not state.get("history_data"):
                            state["history_data"] = {}
                        state["history_data"]["chief_complaint"] = edits.chief_complaint

                    # 编辑 DDx
                    if edits.ddx_edits:
                        ddx_list = state.get("ddx_list", []) or []
                        for edit in edits.ddx_edits:
                            if edit.action == "add" and edit.item:
                                ddx_list.append(edit.item)
                            elif edit.action == "remove" and edit.diagnosis:
                                ddx_list = [d for d in ddx_list
                                            if d.get("diagnosis") != edit.diagnosis]
                            elif edit.action == "reorder" and edit.new_order:
                                name_to_item = {d.get("diagnosis"): d for d in ddx_list}
                                ddx_list = [name_to_item[n] for n in edit.new_order if n in name_to_item]
                        state["ddx_list"] = ddx_list
                        # ★ DDx sentinel: 标记已由医生审阅
                        state["ddx_reviewed"] = True

                    # 编辑过敏史
                    if edits.allergies is not None:
                        state["allergies"] = edits.allergies

                state["doctor_confirm_status"] = decision

            elif review_type == "med_confirm":
                # ── P1c: 医生临床决策 ──
                if body.doctor_action:
                    if body.doctor_action == "adjust" and body.doctor_orders:
                        state.setdefault("medication_adjustments", []).append({
                            "source": "doctor",
                            "action": "adjust",
                            "orders": body.doctor_orders,
                            "timestamp": datetime.now().isoformat(),
                        })
                    elif body.doctor_action == "new_labs" and body.doctor_orders:
                        for lab_order in (body.doctor_orders or {}).get("labs", []):
                            state.setdefault("pending_labs", []).append(lab_order)
                    elif body.doctor_action == "discharge":
                        state["discharge_decision"] = "approved"

                state["med_confirm_status"] = decision

            elif review_type == "discharge_sign":
                # ── P1b: 出院深度 ──
                if decision == "rejected":
                    # 拒签：记录原因 + 设置重评估窗口
                    history = state.get("discharge_reject_history") or []
                    history.append({
                        "timestamp": datetime.now().isoformat(),
                        "reason": body.reject_reason or body.comment,
                    })
                    state["discharge_reject_history"] = history
                    # 重评估窗口：当前 round + 2 后重新尝试
                    current_round = state.get("round_count", 0)
                    state["discharge_reeval_after_rounds"] = current_round + 2
                    state["discharge_decision"] = "pending_reevaluation"
                    state["discharge_sign_status"] = decision
                elif decision in ("signed", "approved"):
                    # 处理 handoff 编辑
                    if body.handoff_edits:
                        handoff_items = state.get("handoff_items", []) or []
                        for edit in body.handoff_edits:
                            if edit.action == "add" and edit.item:
                                handoff_items.append(edit.item)
                            elif edit.action == "remove" and edit.index is not None:
                                if 0 <= edit.index < len(handoff_items):
                                    handoff_items.pop(edit.index)
                            elif edit.action == "edit" and edit.index is not None and edit.item:
                                if 0 <= edit.index < len(handoff_items):
                                    handoff_items[edit.index].update(edit.item)
                        state["handoff_items"] = handoff_items
                    state["discharge_sign_status"] = decision
                else:
                    state["discharge_sign_status"] = decision
            else:
                return UnifiedResponse(
                    data={"error": f"未知审核类型: {review_type}"},
                    error={"code": "INVALID_REVIEW_TYPE"},
                )

            # 清除 pending_review 标志
            state["interrupt_pending"] = False
            state.pop("pending_review", None)

            # 重喂全量 state 续跑 graph（各节点幂等守卫保证跳过已执行节点）
            loop = get_patient_loop(patient_id)
            result = await loop.plan_turn(state)

            # 可能再次触发 pending_review（如下一卡点）
            if isinstance(result, dict) and result.get("status") == "pending_review":
                partial = resolve_pending_state(loop, state, result)
                if request is not None:
                    partial["state_version"] = await _commit_transactional_review(
                        request, patient_id, partial, review_type, decision, body.comment,
                    )
                set_state(patient_id, partial)
                return UnifiedResponse(data={
                    "patient_id": patient_id,
                    "review_type": review_type,
                    "decision": decision,
                    "status": "pending_review",
                    "review_id": result.get("review_id"),
                    "payload": result.get("payload"),
                    "message": "审核已处理，但触发了下一卡点",
                })

            if isinstance(result, dict) and request is not None:
                result["state_version"] = await _commit_transactional_review(
                    request, patient_id, result, review_type, decision, body.comment,
                )
            set_state(patient_id, result)
            return UnifiedResponse(data={
                "patient_id": patient_id,
                "review_type": review_type,
                "decision": decision,
                "status": "resumed",
                "phase": result.get("phase") if isinstance(result, dict) else "unknown",
                "discharge_decision": result.get("discharge_decision") if isinstance(result, dict) else None,
            })


async def _commit_transactional_review(
    request: Request,
    patient_id: str,
    state: dict,
    review_type: str,
    decision: str,
    comment: str | None,
) -> int:
    """Commit the completed review snapshot with its audit fact and outbox intent."""
    from ..services.clinical_facade import clinical_workflow_facade

    return await clinical_workflow_facade.commit(
        request,
        patient_id,
        state,
        action_type="review",
        detail={
            "review_type": review_type,
            "decision": decision,
            "comment": (comment or "")[:200],
        },
        idempotency_scope="review",
    )
