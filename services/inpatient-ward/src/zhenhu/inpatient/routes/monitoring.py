"""体征监测路由 —— 阶段D: 对接Agent, 接收生命体征推送驱动monitoring循环。合并迁入。
阶段G: 接入 AgentLoop, 通过 push 事件注入替代直接调 inpatient_graph。
阶段M Agent升级: AgentEvent 从 contracts 导入。
P1修复: 写入state后触发graph重新评估，实现真正的持续监测→自动出院。
"""

from fastapi import APIRouter

from zhenhu.contracts.agent import AgentEvent

from ..schemas import UnifiedResponse
from ..agent.loop import get_patient_loop

router = APIRouter(prefix="/inpatient", tags=["monitoring"])


@router.post("/monitoring/{patient_id}/vitals")
async def report_vital_signs(patient_id: str, vital_data: dict):
    """上报生命体征并触发Agent监测循环。
    
    P1修复: 写入state后触发graph重新评估，实现真正的持续监测→自动出院。
    """
    from .state_store import get_state, update_state
    from ..agent.loop import get_patient_loop

    state = get_state(patient_id)
    if not state:
        vital_signs = [vital_data]
    else:
        vital_signs = state.get("vital_signs", []) + [vital_data]

    update_state(patient_id, {"vital_signs": vital_signs})

    # 触发 graph 重新评估
    loop = get_patient_loop(patient_id)
    updated_state = get_state(patient_id)
    result = await loop.plan_turn(updated_state)

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "vitals_count": len(vital_signs),
        "phase": result.get("phase"),
        "discharge_decision": result.get("discharge_decision"),
        "alerts": result.get("clinical_alerts", []),
    })


@router.post("/monitoring/{patient_id}/labs")
async def report_lab_results(patient_id: str, lab_data: dict):
    """上报检验结果并触发Agent检验审阅。"""
    from .state_store import get_state, update_state
    from ..agent.loop import get_patient_loop

    state = get_state(patient_id)
    lab_results = (state.get("lab_results", []) if state else []) + [lab_data]
    update_state(patient_id, {"lab_results": lab_results})

    loop = get_patient_loop(patient_id)
    result = await loop.plan_turn(get_state(patient_id))

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "lab_count": len(lab_results),
        "phase": result.get("phase"),
    })
