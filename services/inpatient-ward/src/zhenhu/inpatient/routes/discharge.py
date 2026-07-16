"""出院管理路由——阶段D+: 通过AgentLoop触发出院流程(含trace追踪)。"""

from fastapi import APIRouter

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["discharge"])


@router.post("/discharge/{patient_id}/initiate")
async def initiate_discharge(patient_id: str) -> UnifiedResponse:
    """手动触发出院流程（通过 AgentLoop，含trace追踪）。"""
    from .state_store import get_state, set_state
    from ..agent.loop import get_patient_loop

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(data={"error": "患者入院记录不存在"}, error={"code": "NOT_FOUND"})

    state["discharge_decision"] = "approved"

    loop = get_patient_loop(patient_id)
    result = await loop.plan_turn(state)
    set_state(patient_id, result)

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": result.get("phase"),
        "handoff_items": result.get("handoff_items", []),
        "trace_count": len(loop.traces),
    })
