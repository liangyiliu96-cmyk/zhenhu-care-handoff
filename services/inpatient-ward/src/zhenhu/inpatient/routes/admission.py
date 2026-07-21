"""入院管理路由 —— 阶段D: 对接Agent Graph + 状态存储。合并迁入。
阶段G: 接入 AgentLoop 替代直接调 inpatient_graph。
阶段M Agent升级: AgentEvent 从 contracts 导入。
"""

import logging

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse
from ..agent.loop import get_patient_loop  # 阶段M: 住院特定工厂, 仍在此引入

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["admission"])


@router.post("/admissions")
async def create_admission(
    request: Request,
    patient_id: str = "pat-demo-001",
    disease_id: str = "hypertension",
) -> UnifiedResponse:
    """创建入院记录并启动Agent全流程。

    阶段D: 从fixture升级为真实Agent调用, 结果写入状态存储。
    阶段G: 接入 AgentLoop, 通过 gen_input("new_admission") 生成初始状态。
    """
    from ..agent.nodes import load_template
    from ..agent.loop import get_patient_lock, resolve_pending_state
    from .state_store import set_state
    from ..services.clinical_facade import clinical_workflow_facade

    # ── O6: 持锁包裹 gen_input → plan_turn → set_state ──
    lock = get_patient_lock(patient_id)
    async with lock:
        template = load_template(disease_id)

        loop = get_patient_loop(patient_id)
        initial_state = loop.gen_input("new_admission")
        initial_state["patient_id"] = patient_id
        initial_state["disease_template"] = template
        from ..services.patient_access import bind_patient_access
        bind_patient_access(initial_state, getattr(request.state, "user_info", None))

        result = await loop.plan_turn(initial_state)
        persisted_state = (
            resolve_pending_state(loop, initial_state, result)
            if result.get("status") == "pending_review"
            else result
        )

        persisted_state["state_version"] = await clinical_workflow_facade.commit(
            request,
            patient_id,
            persisted_state,
            action_type="admission_created",
            detail={"disease_id": disease_id, "phase": persisted_state.get("phase")},
            idempotency_scope="admission_created",
        )
        set_state(patient_id, persisted_state)
        logger.info("Admission created: patient_id=%s phase=%s", patient_id, persisted_state.get("phase"))
        return UnifiedResponse(data={
            "patient_id": patient_id,
            "phase": persisted_state.get("phase"),
            "final_phase": persisted_state.get("phase"),
            "risk_level": persisted_state.get("risk_level"),
            "discharge_decision": persisted_state.get("discharge_decision"),
            "handoff_items": persisted_state.get("handoff_items", []),
            "mdt_required": persisted_state.get("mdt_required", False),
        })


@router.get("/admissions/{patient_id}")
async def get_admission(patient_id: str):
    """查询入院状态（阶段D: 从状态存储返回真实Agent结果）。"""
    from .state_store import get_state
    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到患者状态: {patient_id}"})
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": state.get("phase"),
        "risk_level": state.get("risk_level"),
        "discharge_decision": state.get("discharge_decision"),
        "handoff_items": state.get("handoff_items", []),
        "mdt_required": state.get("mdt_required", False),
        "document_chain": state.get("document_chain", []),
    })
