"""Low-risk LLM drafts for MDT, follow-up, and transfer coordination."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .llm_utils import deep_invoke, get_provider_for_node

_TITLES = {
    "mdt": "MDT 会前简报",
    "follow_up": "随访脚本与问卷草稿",
    "transfer": "转科交接草稿",
}


async def build_workflow_brief(state: dict, kind: str) -> dict:
    """Generate a read-only coordination draft with a deterministic fallback."""
    if kind not in _TITLES:
        raise ValueError(f"unsupported brief kind: {kind}")

    template = state.get("disease_template") or {}
    vitals = state.get("vital_signs") or []
    labs = state.get("lab_results") or []
    latest = vitals[-1] if vitals else {}
    alerts = state.get("clinical_alerts") or []
    care = {
        "mdt_requests": state.get("mdt_requests") or [],
        "follow_up_tasks": state.get("follow_up_tasks") or [],
        "transfer_target": state.get("transfer_target"),
        "transfer_reason": state.get("transfer_reason"),
    }
    context = {
        "病种": template.get("name") or template.get("disease_id") or "未标注病种",
        "风险": state.get("risk_level") or "未分层",
        "最新体征": latest,
        "最近检验": labs[-5:],
        "未解决告警": alerts[-6:],
        "当前诊疗": state.get("medication_adjustments") or [],
        "协同状态": care,
    }
    fallback = _fallback(kind, context)
    prompt = (
        f"你是住院协同中的临床文书助手。请基于已记录数据生成《{_TITLES[kind]}》。"
        "只能总结已给出的事实，不能编造诊断、检查结果、医嘱、时间或联系方式。"
        "内容是待医生/护士确认的草稿，不能替代临床决策。请用中文，分点写，最多 6 条。\n\n"
        f"患者上下文：{json.dumps(context, ensure_ascii=False, default=str)[:5000]}"
    )
    citations: list[dict] = []
    content = fallback
    source = "rule_based"
    try:
        result = await deep_invoke(
            get_provider_for_node(f"workflow_brief_{kind}"),
            prompt,
            context={"workflow_brief": kind, "patient_context": context},
            rag_query=f"{context['病种']} {kind} 临床协同要点",
            caller=f"workflow_brief_{kind}",
            timeout=18.0,
        )
        candidate = str((result or {}).get("response") or "").strip()
        if candidate:
            content = candidate
            source = "llm_rag"
        citations = list((result or {}).get("_rag_citations") or [])
    except Exception:
        pass
    return {
        "kind": kind,
        "title": _TITLES[kind],
        "content": content,
        "citations": citations,
        "generation_source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
    }


def _fallback(kind: str, context: dict) -> str:
    disease = context["病种"]
    alerts = context["未解决告警"]
    if kind == "mdt":
        return f"- 会诊主题：{disease}的复杂诊疗协同\n- 请重点讨论：当前风险、异常检验与治疗反应\n- 已记录告警：{len(alerts)} 条，需逐项核对后决定处置。"
    if kind == "transfer":
        care = context["协同状态"]
        return f"- 转科目标：{care.get('transfer_target') or '待医生确定'}\n- 转科原因：{care.get('transfer_reason') or '请结合当前风险与监测结果补充'}\n- 交接重点：最近体征、异常检验、当前治疗与未完成事项。"
    return f"- 随访主题：{disease}出院后症状与依从性核对\n- 建议询问：症状变化、用药执行、体重/血压等自测情况及异常警讯\n- 如出现告警症状，请按既有随访升级流程处理。"
