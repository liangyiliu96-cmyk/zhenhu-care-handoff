"""管理路由 —— 阶段D: 病种模板管理、系统状态等管理功能。合并迁入。

提供 GET /inpatient/templates 列出所有可用病种模板(JSON 配置化)。
提供 POST /inpatient/fixtures/load/{patient_key} 一键加载预置患者并执行完整入院→出院流程。
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter
from ..schemas import UnifiedResponse
from .patient_fixtures import PATIENTS

# 合并迁入: 直接引用 disease_templates 目录, 不依赖 app.domain.templates
_TEMPLATE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "disease_templates")).resolve()

router = APIRouter(prefix="/inpatient", tags=["admin"])


@router.get("/templates")
async def list_templates():
    """列出所有可用病种模板。"""
    templates = []
    for f in sorted(_TEMPLATE_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        templates.append({"disease_id": d["disease_id"], "name": d["name"]})
    return UnifiedResponse(data={"templates": templates})


@router.post("/fixtures/load/{patient_key}")
async def load_fixture_patient(patient_key: str):
    """加载预置患者数据并执行完整入院→出院流程。"""
    if patient_key not in PATIENTS:
        return UnifiedResponse(data={"error": f"未知患者: {patient_key}"}, error={"code": "NOT_FOUND"})

    from ..agent.loop import get_patient_loop
    from ..agent.nodes import load_template
    from .state_store import set_state, get_state, update_state

    p = PATIENTS[patient_key]

    # 1. 创建入院
    loop = get_patient_loop(patient_key)
    state = loop.gen_input("new_admission")
    state["patient_id"] = patient_key
    state["patient_data"] = p["patient_data"]
    state["patient_history"] = p["patient_history"]
    state["allergies"] = p["allergies"]
    state["disease_template"] = load_template(p["disease_id"])

    result = await loop.plan_turn(state)
    set_state(patient_key, result)

    # 2. 逐步上报体征
    for i, vs in enumerate(p["vital_signs_sequence"]):
        current = get_state(patient_key)
        vss = current.get("vital_signs", []) + [vs]
        update_state(patient_key, {"vital_signs": vss})
        result = await loop.plan_turn(get_state(patient_key))
        set_state(patient_key, result)

        # 如果已自动出院，提前退出
        if result.get("phase") in ("discharge", "handoff", "review", "confirm"):
            break

    return UnifiedResponse(data={
        "patient_key": patient_key,
        "name": p["name"],
        "disease": p["disease_id"],
        "final_phase": result.get("phase"),
        "vital_signs_count": len(result.get("vital_signs", [])),
        "handoff_items": len(result.get("handoff_items", [])),
        "discharge_decision": result.get("discharge_decision"),
        "document_chain": result.get("document_chain", []),
        "traces": len(loop.traces),
    })
