"""自然语言患者查询 — POST /inpatient/{id}/query。

医生用自然语言问患者状态，LLM 读 state 回答。
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from ..agent.llm_utils import deep_invoke, get_provider_for_node
from .route_schemas import QueryRequest

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["query"])


@router.post("/{patient_id}/query")
async def query_patient(patient_id: str, body: QueryRequest, request: Request):
    from .state_store import get_state
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})

    # 构建上下文摘要
    history_data = state.get("history_data") or {}
    pe_data = state.get("pe_data") or {}
    hpi = state.get("hpi_narrative") or history_data.get("hpi_narrative") or ""
    pe = state.get("pe_narrative") or pe_data.get("pe_narrative") or ""
    vs = state.get("vital_signs", []) or []
    latest_vs = vs[-1] if vs else {}
    alerts = state.get("clinical_alerts", []) or []
    ddx = state.get("ddx_list", []) or []
    round_count = state.get("round_count", 0)
    phase = state.get("phase", "")
    discharge_decision = state.get("discharge_decision", "")
    tpl = state.get("disease_template", {}) or {}
    labs = state.get("lab_results", []) or []
    medications = state.get("medication_adjustments", []) or []
    latest_round = state.get("latest_round") or {}
    pending_review = state.get("pending_review") if isinstance(state.get("pending_review"), dict) else {}

    def compact(value) -> str:
        if isinstance(value, dict):
            return str(value.get("message") or value.get("content") or value.get("type") or value)
        return str(value)

    context = (
        f"患者诊断: {tpl.get('name') or tpl.get('disease_id', '未知')}\n"
        f"风险等级: {state.get('risk_level', '')}\n"
        f"当前阶段: {phase}\n"
        f"查房轮次: {round_count}\n"
        f"出院决定: {discharge_decision or '未决定'}\n"
        f"现病史: {hpi[:300] if hpi else '未记录'}\n"
        f"查体: {pe[:300] if pe else '未记录'}\n"
        f"最新体征: {json.dumps(latest_vs, ensure_ascii=False)[:200]}\n"
        f"临床告警({len(alerts)}): {'; '.join(compact(item) for item in alerts[-5:]) or '无'}\n"
        f"鉴别诊断: {', '.join(d.get('diagnosis', '') for d in ddx[:4])}\n"
        f"最近检验: {json.dumps(labs[-5:], ensure_ascii=False)[:500] if labs else '无'}\n"
        f"当前用药调整: {json.dumps(medications[-5:], ensure_ascii=False)[:500] if medications else '无'}\n"
        f"最近查房评估: {json.dumps(latest_round, ensure_ascii=False)[:800] if latest_round else '无'}\n"
        f"待审核卡点: {pending_review.get('type') or '无'}\n"
    )

    try:
        provider = get_provider_for_node("patient_query")
        prompt = (
            f"你是一位住院医生，正在查看一位住院患者的临床数据。请用中文回答以下问题。\n\n"
            f"【患者临床数据】\n{context}\n\n"
            f"【医生的问题】{body.question}\n\n"
            f"请先给出结论，再列出最多3条依据和下一步建议。不得编造患者未记录的数据。"
        )
        result = await deep_invoke(
            provider,
            prompt,
            rag_query=body.question,
            caller="patient_query",
            timeout=15.0,
        )
        answer = (result or {}).get("response", "") if result else ""
        citations = list((result or {}).get("_rag_citations", []) or [])
        if not answer:
            answer = "抱歉，暂时无法回答此问题。"
    except Exception:
        logger.exception("query_patient LLM invoke failed for %s", patient_id)
        answer = "抱歉，查询服务暂时不可用。"
        citations = []

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "question": body.question,
        "answer": answer,
        "citations": citations,
    })
