"""Agent 工具封装 —— 已废弃。

阶段J审计: search_knowledge 由节点直调 bridge_search_knowledge,
check_discharge_criteria 由 node_discharge 内联实现。
保留签名为阶段5 LLM工具调用预留。
"""


async def search_knowledge(query: str, top_k: int = 10) -> list[dict]:
    """调用知识库检索 —— 阶段5: LLM工具调用预留。

    阶段J审计: 当前由 node_analyse 直调 bridge_search_knowledge，
    不走 tools 层。此签名保留供阶段5 LangChain 工具封装使用。
    """
    raise NotImplementedError("阶段5: LLM工具调用预留")


async def check_discharge_criteria(template: dict, vital_history: list) -> bool:
    """对照病种模板检查出院条件 —— 阶段5: LLM工具调用预留。

    阶段J审计: 当前由 node_discharge 内联实现出院判断逻辑。
    此签名保留供阶段5 规则引擎封装使用。
    """
    raise NotImplementedError("阶段5: LLM工具调用预留")
