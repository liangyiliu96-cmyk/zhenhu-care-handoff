"""入院管理路由 —— 阶段D: 对接Agent Graph + 状态存储。合并迁入。
阶段G: 接入 AgentLoop 替代直接调 inpatient_graph。
阶段M Agent升级: AgentEvent 从 contracts 导入。
"""

from fastapi import APIRouter

from ..schemas import UnifiedResponse
from ..agent.loop import get_patient_loop  # 阶段M: 住院特定工厂, 仍在此引入

router = APIRouter(prefix="/inpatient", tags=["admission"])


@router.post("/admissions")
async def create_admission(
    patient_id: str = "pat-demo-001",
    disease_id: str = "hypertension",
) -> UnifiedResponse:
    """创建入院记录并启动Agent全流程。

    阶段D: 从fixture升级为真实Agent调用, 结果写入状态存储。
    阶段G: 接入 AgentLoop, 通过 gen_input("new_admission") 生成初始状态。
    """
    from ..agent.nodes import load_template

    template = load_template(disease_id)

    loop = get_patient_loop(patient_id)
    initial_state = loop.gen_input("new_admission")
    initial_state["patient_id"] = patient_id
    initial_state["disease_template"] = template

    result = await loop.plan_turn(initial_state)

    from .state_store import set_state
    set_state(patient_id, result)
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": result.get("phase"),
        "final_phase": result.get("phase"),
        "risk_level": result.get("risk_level"),
        "discharge_decision": result.get("discharge_decision"),
        "handoff_items": result.get("handoff_items", []),
        "mdt_required": result.get("mdt_required", False),
    })


@router.get("/admissions/{patient_id}")
async def get_admission(patient_id: str):
    """查询入院状态（阶段D: 从状态存储返回真实Agent结果）。"""
    from .state_store import get_state
    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(data={"patient_id": patient_id, "status": "not_found"})
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": state.get("phase"),
        "risk_level": state.get("risk_level"),
        "discharge_decision": state.get("discharge_decision"),
        "handoff_items": state.get("handoff_items", []),
        "mdt_required": state.get("mdt_required", False),
        "document_chain": state.get("document_chain", []),
    })
