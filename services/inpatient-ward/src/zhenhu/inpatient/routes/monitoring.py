"""体征监测路由 —— 阶段D: 对接Agent, 接收生命体征推送驱动monitoring循环。合并迁入。
阶段G: 接入 AgentLoop, 通过 push 事件注入替代直接调 inpatient_graph。
阶段M Agent升级: AgentEvent 从 contracts 导入。
"""

from fastapi import APIRouter

from zhenhu.contracts.agent import AgentEvent

from ..schemas import UnifiedResponse
from ..agent.loop import get_patient_loop

router = APIRouter(prefix="/inpatient", tags=["monitoring"])


@router.post("/monitoring/{patient_id}/vital-signs")
async def report_vital_signs(patient_id: str, vital_data: dict):
    """上报生命体征——驱动Agent monitoring循环（阶段D: 从fixture升级）。
    阶段G: 接入 AgentLoop, push 事件注入。
    """
    from .state_store import get_state, update_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(data={"error": "患者入院记录不存在"}, error={"code": "NOT_FOUND"})

    vs_list = state.get("vital_signs", [])
    vs_list.append(vital_data)

    update_state(patient_id, {"vital_signs": vs_list})

    event = AgentEvent(event_type="vital_sign", source="nurse_station")
    loop = get_patient_loop(patient_id)
    loop.push(event)

    result = await loop.plan_turn(state)
    update_state(patient_id, result)

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "vital_count": len(vs_list),
        "phase": result.get("phase"),
        "discharge_decision": result.get("discharge_decision"),
        "message": "体征已记录, Agent已重新评估" if result.get("discharge_decision") != "approved" else "体征已记录, 满足出院条件"
    })


@router.post("/monitoring/{patient_id}/lab-results")
async def report_lab_results(patient_id: str, lab_data: dict):
    """上报检验/检查结果——驱动Agent lab_review节点。

    阶段E: 补齐缺失临床步骤。
    阶段G: 接入 AgentLoop, push 事件注入。
    """
    from .state_store import get_state, update_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(data={"error": "患者入院记录不存在"}, error={"code": "NOT_FOUND"})

    labs = state.get("lab_results", [])
    labs.append(lab_data)

    update_state(patient_id, {"lab_results": labs})

    event = AgentEvent(event_type="lab_result", source="nurse_station")
    loop = get_patient_loop(patient_id)
    loop.push(event)

    result = await loop.plan_turn(state)
    update_state(patient_id, result)

    return UnifiedResponse(data={"patient_id": patient_id, "lab_count": len(labs), "phase": result.get("phase")})
