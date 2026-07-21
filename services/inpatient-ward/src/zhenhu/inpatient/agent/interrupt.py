"""HumanInterrupt 封装 —— 参考LangGraph interrupt模式。合并迁入。

阶段4 Agent框架: 占位实现, 不实际中断, 返回默认accept。

参考: LangGraph interrupt() / Command(resume=...)

langgraph 已安装，interrupt/Command 可正常 import。
持久 interrupt（跨进程 resume）需 SqliteSaver：
    pip install langgraph-checkpoint-sqlite（见 §16.2 钉版本）。
当前默认 GRAPH_MODE=classic 下采用 state_store pending_review 手动挂起，
无需持久 checkpointer。
"""

import uuid

from .config import get_graph_mode, is_doctor_auto_approve


async def request_doctor_review(handoff_items: list[dict]) -> dict:
    """请求医生审核（双模）。

    classic 模式（默认）：
        若 DOCTOR_AUTO_APPROVE=true → 返回 {"action":"accept","items":...}
        否则 → 返回 {"action":"pending","pending_review":{...}}
    stateful 模式（Phase-2）：
        使用 LangGraph 原生 interrupt() 挂起图执行。
    """
    graph_mode = get_graph_mode()

    if graph_mode == "stateful":
        # Phase-2: 原生 interrupt() 挂起
        try:
            from langgraph.types import interrupt
            interrupt({"action": "pending", "items": handoff_items})
        except ImportError:
            pass  # fall through to classic behavior

    # classic 模式（默认）
    if is_doctor_auto_approve():
        return {"action": "accept", "items": handoff_items}

    review_id = f"review-{uuid.uuid4().hex[:12]}"
    return {
        "action": "pending",
        "pending_review": {
            "review_id": review_id,
            "review_type": "doctor_confirm",
            "items": handoff_items,
            "status": "pending",
        },
    }
