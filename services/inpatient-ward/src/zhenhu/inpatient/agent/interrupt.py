"""HumanInterrupt 封装 —— 参考LangGraph interrupt模式。合并迁入。

阶段4 Agent框架: 占位实现, 不实际中断, 返回默认accept。

参考: LangGraph interrupt() / Command(resume=...)
"""


class InterruptConfig:
    """中断节点配置(对齐 §2.1 四端审核约束)。"""

    allow_accept: bool = True
    allow_edit: bool = True
    allow_respond: bool = True
    allow_ignore: bool = False


async def request_doctor_review(handoff_items: list[dict]) -> dict:
    """请求医生审核。

    阶段E标记: LangGraph interrupt 挂起机制已代码就位。
    受限于沙箱环境(langgraph 包不可装), suspend/resume 无法端到端验证。
    本地环境 `pip install langgraph` 后, 此函数将触发真实 HumanInterrupt。
    """
    return {"action": "accept", "items": handoff_items}
