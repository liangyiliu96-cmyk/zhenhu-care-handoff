"""临床叙事端点 — GET /inpatient/{id}/clinical-note。

返回患者完整的入院临床文书：主诉(CC)、现病史(HPI)、体格检查(PE)、
系统回顾(ROS)、过敏史、既往史(PMH)、家族史(FH)、社会史(SH)。
可选 ?narrative=true 触发 LLM 生成完整入院记录叙事段落。
纯读 state_store，零副作用。前端可直接渲染为入院记录文本。
"""

import logging

from fastapi import APIRouter, Query

from ..schemas import UnifiedResponse

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["clinical"])


@router.get("/{patient_id}/clinical-note")
async def get_clinical_note(patient_id: str, narrative: bool = Query(default=False)):
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    hx = state.get("history_data") or {}
    pe_d = state.get("pe_data") or {}
    result = {
        "patient_id": patient_id,
        "chief_complaint": hx.get("chief_complaint") or state.get("chief_complaint", ""),
        "hpi_narrative": state.get("hpi_narrative") or hx.get("hpi_narrative", ""),
        "pe_narrative": state.get("pe_narrative") or pe_d.get("pe_narrative", ""),
        "allergies": state.get("allergies") or hx.get("allergies", []),
        "ros_findings": state.get("ros_findings") or hx.get("ros_findings"),
        "pmh": hx.get("pmh") or state.get("patient_history", {}).get("comorbidities"),
        "fh": hx.get("fh"),
        "sh": hx.get("sh"),
    }

    # LLM 生成完整入院记录叙事
    if narrative and (hx or state.get("hpi_narrative")):
        import json as _json
        try:
            from ..agent.config import get_cached_provider
            from ..agent.llm_utils import safe_llm_invoke
            provider = get_cached_provider()
            cc = result["chief_complaint"]
            hpi = result["hpi_narrative"] or ""
            pe = result["pe_narrative"] or ""
            prompt = (
                f"基于以下临床数据生成一份中文入院记录的主诉+现病史+体格检查部分(200字以内)：\n"
                f"主诉: {cc}\n现病史: {hpi[:300]}\n体格检查: {pe[:300]}\n"
                f"过敏史: {_json.dumps(result['allergies'], ensure_ascii=False)}\n"
                f"请返回JSON: {{\"admission_note\": \"...\"}}"
            )
            llm_result = await safe_llm_invoke(provider, prompt, timeout=10.0)
            note = (llm_result or {}).get("response") or (llm_result or {}).get("admission_note") or ""
            if note:
                result["admission_note"] = note
        except Exception:
            result["admission_note"] = f"{cc}。{hpi[:100]}..."

    return UnifiedResponse(data=result)
