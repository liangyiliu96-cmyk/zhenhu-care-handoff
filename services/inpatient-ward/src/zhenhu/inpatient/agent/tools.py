"""Agent 工具封装 —— RAG检索 + 出院标准检查。合并迁入。

阶段G: search_knowledge 从 fixture 升级为真实臻护桥接调用。
"""

from ..hooks.zhenhu_bridge import bridge_search_knowledge


async def search_knowledge(query: str, top_k: int = 10) -> list[dict]:
    """调用知识库检索——对接臻护 knowledge-orchestrator。

    阶段G: 替换 fixture 空返回, 调 bridge_search_knowledge → GET /knowledge/search。
    失败时降级为空列表, 不阻断 Agent 流程。
    """
    return await bridge_search_knowledge(query, top_k)


async def check_discharge_criteria(template: dict, vital_history: list) -> bool:
    """对照病种模板检查出院条件(fixture)。

    阶段5: 对接病种模板 discharge_criteria 规则引擎。
    """
    criteria = template.get("discharge_criteria", [])
    return len(vital_history) >= len(criteria)
