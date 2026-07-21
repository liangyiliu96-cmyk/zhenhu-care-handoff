"""录入闭环端点 —— v1.3 §七 Batch C2。

承接医生/护士人工录入病史、体格检查、护理数据。
classic 模式：写入 state_store → plan_turn 重喂全量 state 续跑 graph。
stateful 模式（Phase-2）：经 graph.update_state 注入增量后续跑。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from .route_schemas import HistoryRequest, PhysicalExamRequest, NursingRequest

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["admission_clinical"])


@router.post("/admissions/{patient_id}/history")
async def record_history(patient_id: str, data: HistoryRequest, request: Request):
    """录入 CC/HPI/PMH/FH/SH/ROS — v1.3 §七。

    写入 state_store，触发 graph 续跑。
    node_history_taking 幂等守卫检测 history_data 已存在 → 跳过。
    """
    return await _record_clinical_input(
        request, patient_id, data, "history_data", "history_entered", "history_recorded",
    )


@router.post("/admissions/{patient_id}/physical-exam")
async def record_physical_exam(patient_id: str, data: PhysicalExamRequest, request: Request):
    """录入体格检查数据 — v1.3 §七。

    写入 state_store，触发 graph 续跑。
    node_physical_exam 幂等守卫检测 pe_data 已存在 → 跳过。
    """
    return await _record_clinical_input(
        request, patient_id, data, "pe_data", "physical_exam_entered", "physical_exam_recorded",
    )


@router.post("/admissions/{patient_id}/nursing")
async def record_nursing(patient_id: str, data: NursingRequest, request: Request):
    """录入护理数据 — v1.3 §七。

    写入 state_store，触发 graph 续跑。
    node_nursing 幂等守卫检测 nursing_records 已存在 → 跳过。
    """
    return await _record_clinical_input(
        request, patient_id, data, "nursing_records", "nursing_entered", "nursing_recorded",
        append=True,
    )


async def _record_clinical_input(
    request: Request,
    patient_id: str,
    data: HistoryRequest | PhysicalExamRequest | NursingRequest,
    state_key: str,
    document_event: str,
    action_type: str,
    *,
    append: bool = False,
) -> UnifiedResponse:
    """Persist a manual clinical fact and the graph result in one workflow commit."""
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    payload = data.model_dump(exclude={"expected_version"})
    is_nursing_record = isinstance(data, NursingRequest)
    if is_nursing_record:
        payload.update({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "manual",
            "action": payload.get("nursing_actions", ""),
        })

    def apply(state: dict) -> None:
        if append:
            state[state_key] = [*(state.get(state_key) or []), payload]
        else:
            state[state_key] = payload
        if is_nursing_record and payload.get("vital_signs"):
            state["vital_signs"] = [*(state.get("vital_signs") or []), {
                **payload["vital_signs"],
                "timestamp": payload["timestamp"],
                "source": "nursing_record",
            }]
        state["document_chain"] = [*(state.get("document_chain") or []), document_event]

    async def plan_nursing(state: dict, loop) -> dict:
        """Run the focused monitoring path for bedside observations.

        The admission graph starts from history and DDx nodes. Replaying it for
        every nursing observation delays the write behind unrelated LLM calls.
        """
        focused_planner = getattr(loop, "plan_monitoring_turn", None)
        if callable(focused_planner):
            return await focused_planner(state, event_type="nursing", collect=False)
        return await loop.plan_turn(state)

    try:
        result, _ = await patient_state_service.plan_clinical(
            request,
            patient_id,
            apply,
            action_type=action_type,
            detail={"field": state_key, "vital_signs_recorded": bool(payload.get("vital_signs"))},
            idempotency_scope=action_type,
            planner=plan_nursing if is_nursing_record else None,
            expected_version=data.expected_version,
        )
    except PatientNotFoundError:
        return UnifiedResponse(
            data={"error": f"未找到患者状态: {patient_id}"},
            error={"code": "NOT_FOUND"},
        )

    if isinstance(result, dict) and result.get("status") == "pending_review":
        return UnifiedResponse(data={
            "status": "ok",
            "phase": result.get("phase"),
            "pending_review": True,
            "review_id": result.get("review_id"),
            "payload": result.get("payload"),
        })
    return UnifiedResponse(data={
        "status": "ok",
        "phase": result.get("phase", "unknown") if isinstance(result, dict) else "unknown",
    })
