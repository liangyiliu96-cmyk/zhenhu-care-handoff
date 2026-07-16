"""出院管理路由 —— 阶段D: 手动触发出院流程, 对接Agent Graph。合并迁入。"""

import httpx
from fastapi import APIRouter

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["discharge"])


@router.post("/discharge/{patient_id}/initiate")
async def initiate_discharge(patient_id: str):
    """手动触发出院流程（阶段D: 从fixture升级为Agent驱动）。"""
    from .state_store import get_state, set_state
    from ..agent.graph import inpatient_graph
    from ..hooks.zhenhu_bridge import bridge_discharge_to_zhenhu_with_retry, FHIR_URL

    if inpatient_graph is None:
        return UnifiedResponse(data={"status": "langgraph_unavailable"})

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(data={"error": "患者入院记录不存在"}, error={"code": "NOT_FOUND"})

    # 强制设置出院决策, 走 full discharge→handoff→review→confirm 链
    state["discharge_decision"] = "approved"
    result = await inpatient_graph.ainvoke(state)
    set_state(patient_id, result)

    bridge_result = await bridge_discharge_to_zhenhu_with_retry(
        result.get("handoff_items", []), patient_id, state.get("disease_template", {})
    )
    result["bridge_result"] = bridge_result
    result["bridge_status"] = bridge_result.get("status", "unknown")
    if bridge_result.get("status") == "bridge_unavailable":
        result["discharge_decision"] = "bridge_failed"
        result["bridge_error"] = "臻护workflow-engine不可达，病例未创建，请手动重试"

    # 患者照护视图 — 从 FHIR-adapter 获取, 失败不阻断出院流程
    care_view = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{FHIR_URL}/patient/{patient_id}/care-view")
            if resp.status_code == 200:
                care_view = resp.json().get("data", {})
    except Exception:
        pass

    result["care_view"] = care_view

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": result.get("phase"),
        "final_phase": result.get("phase"),
        "handoff_items": result.get("handoff_items", []),
        "mdt_required": result.get("mdt_required", False),
        "bridge_status": bridge_result.get("status"),
        "bridge_case_id": bridge_result.get("case_id"),
        "bridge_error": bridge_result.get("bridge_error"),
        "care_view": care_view,
    })
