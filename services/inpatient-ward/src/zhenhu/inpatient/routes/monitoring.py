"""体征监测路由 —— 阶段D: 对接Agent, 接收生命体征推送驱动monitoring循环。合并迁入。
阶段G: 接入 AgentLoop, 通过 push 事件注入替代直接调 inpatient_graph。
阶段M Agent升级: AgentEvent 从 contracts 导入。
P1修复: 写入state后触发graph重新评估，实现真正的持续监测→自动出院。
"""

from fastapi import APIRouter

from zhenhu.contracts.agent import AgentEvent

from ..schemas import UnifiedResponse
from ..agent.loop import get_patient_loop
from .route_schemas import VitalSignsRequest, LabResultsRequest

router = APIRouter(prefix="/inpatient", tags=["monitoring"])


@router.post("/monitoring/{patient_id}/vitals")
async def report_vital_signs(patient_id: str, vital_data: VitalSignsRequest):
    """上报生命体征并触发Agent监测循环。
    
    P1修复: 写入state后触发graph重新评估，实现真正的持续监测→自动出院。
    """
    from .state_store import get_state, set_state, update_state
    from ..agent.loop import get_patient_loop

    vital_dict = vital_data.model_dump(exclude_none=True)

    state = get_state(patient_id)
    if not state:
        vital_signs = [vital_dict]
    else:
        vital_signs = state.get("vital_signs", []) + [vital_dict]

    update_state(patient_id, {"vital_signs": vital_signs})

    # 直调monitoring节点评估出院标准
    from ..agent.nodes_monitoring import node_monitoring
    state = get_state(patient_id)
    mon_result = await node_monitoring(state)
    state = {**state, **mon_result}
    update_state(patient_id, mon_result)

    # 自动出院: monitoring批准→直调discharge链路
    if state.get("discharge_decision") == "approved":
        from ..agent.nodes_handoff import node_discharge, node_handoff, node_doctor_review, node_patient_confirm
        state = {**state, **await node_discharge(state)}
        state = {**state, **await node_handoff(state)}
        state = {**state, **await node_doctor_review(state)}
        state = {**state, **await node_patient_confirm(state)}
        set_state(patient_id, state)

        return UnifiedResponse(data={
            "patient_id": patient_id,
            "vitals_count": len(vital_signs),
            "phase": state.get("phase"),
            "auto_discharge": True,
            "discharge_decision": state.get("discharge_decision"),
            "handoff_items": state.get("handoff_items", []),
        })

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "vitals_count": len(vital_signs),
        "phase": state.get("phase"),
        "discharge_decision": state.get("discharge_decision"),
        "alerts": state.get("clinical_alerts", []),
    })


@router.post("/monitoring/{patient_id}/labs")
async def report_lab_results(patient_id: str, lab_data: LabResultsRequest):
    """上报检验结果并触发Agent检验审阅。"""
    from .state_store import get_state, set_state, update_state
    from ..agent.loop import get_patient_loop

    lab_dict = lab_data.model_dump(exclude_none=True)

    state = get_state(patient_id)
    lab_results = (state.get("lab_results", []) if state else []) + [lab_dict]
    update_state(patient_id, {"lab_results": lab_results})

    loop = get_patient_loop(patient_id)
    result = await loop.plan_turn(get_state(patient_id))

    # graph重评估后检查是否自动出院
    if result.get("discharge_decision") == "approved":
        discharge_state = get_state(patient_id)
        discharge_state["discharge_decision"] = "approved"
        set_state(patient_id, discharge_state)
        discharge_result = await loop.plan_turn(discharge_state)
        set_state(patient_id, discharge_result)

        return UnifiedResponse(data={
            "patient_id": patient_id,
            "lab_count": len(lab_results),
            "phase": discharge_result.get("phase"),
            "auto_discharge": True,
            "discharge_decision": discharge_result.get("discharge_decision"),
            "handoff_items": discharge_result.get("handoff_items", []),
        })

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "lab_count": len(lab_results),
        "phase": result.get("phase"),
    })
