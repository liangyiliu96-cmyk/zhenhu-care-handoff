"""Agent 工具封装 — Phase5: LLM工具调用实现。"""

import json as _json

from .llm_utils import get_provider_for_node, safe_llm_invoke  # P1-4


async def search_knowledge(query: str, top_k: int = 10) -> list[dict]:
    """调用知识库检索 + LLM 后处理。

    阶段5: 先调用 knowledge-orchestrator 的混合检索，
    再用 LLM 对结果做重排序和摘要。
    """
    try:
        # 1. 知识库检索（HTTP fallback）
        from ..hooks.zhenhu_bridge import bridge_search_knowledge
        raw_results = await bridge_search_knowledge(query) or []

        # 2. LLM 重排序+摘要
        if raw_results:
            provider = get_provider_for_node("knowledge_rerank")
            llm_result = await safe_llm_invoke(
                provider,
                f"对以下检索结果重排序，选出最相关{min(top_k, len(raw_results))}条并生成摘要。query={query}",
                context={"raw_results": raw_results, "top_k": top_k},
                timeout=10.0,
                retries=0,
                caller="knowledge_rerank",
            )
            if llm_result and llm_result.get("source_type") != "source_none":
                return llm_result.get("results", raw_results[:top_k])

        return raw_results[:top_k]
    except Exception:
        return []


async def check_discharge_criteria(template: dict, vital_history: list) -> bool:
    """用 LLM 对照病种模板检查出院条件。

    阶段5: 替代 _evaluate_criterion 的逐条规则匹配，
    一次性让 LLM 评估所有出院标准。
    """
    try:
        provider = get_provider_for_node("discharge_criteria")
        criteria = template.get("discharge_criteria", [])
        if not criteria:
            return False
        result = await safe_llm_invoke(
            provider,
            f"判断患者是否满足所有出院标准。标准列表: {_json.dumps(criteria, ensure_ascii=False)}。"
            f"体征历史: {_json.dumps(vital_history[-5:], ensure_ascii=False)}。"
            f"返回JSON: {{\"all_met\": true/false, \"details\": [...]}}",
            context={"disease_template": template, "vital_signs": vital_history},
            timeout=10.0,
            retries=0,
            caller="discharge_criteria",
        )
        if result and result.get("source_type") != "source_none":
            return bool(result.get("all_met", False))
        return False
    except Exception:
        return False
