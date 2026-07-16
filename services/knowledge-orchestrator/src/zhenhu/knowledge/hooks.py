"""反向阻断钩子 —— 知识变更后通知受影响的病例。

当知识文档被撤回、过期或替代时，异步通知 workflow-engine，
将引用该知识的在办病例转入 knowledge_changed 状态。通知失败不阻塞主流程。
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# workflow-engine 的内部钩子入口地址（可通过 WORKFLOW_ENGINE_URL 环境变量覆盖）
_WORKFLOW_ENGINE_HOOK_URL = os.environ.get(
    "WORKFLOW_ENGINE_URL",
    "http://localhost:8000/hooks/knowledge-changed",
)


async def notify_knowledge_changed(
    document_id: str,
    version: str,
    actor: str = "knowledge_admin",
) -> dict | None:
    """通知 workflow-engine 知识已变更。

    当知识文档进入终态（过期/撤回/被替代/归档），向 workflow-engine 发送 POST 请求。
    失败时仅记录日志，不抛异常，不阻塞知识状态转移。

    Args:
        document_id: 已变更的知识文档 ID。
        version: 文档版本号。
        actor: 操作者身份。

    Returns:
        成功时返回响应字典 { "blocked_count": int }，失败时返回 None。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _WORKFLOW_ENGINE_HOOK_URL,
                json={
                    "document_id": document_id,
                    "version": version,
                    "actor": actor,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info(
                    "知识变更通知已送达：document_id=%s, blocked_count=%s",
                    document_id,
                    data.get("blocked_count", 0),
                )
                return data
            else:
                logger.warning(
                    "知识变更通知被拒绝：document_id=%s, status=%s",
                    document_id,
                    resp.status_code,
                )
                return None
    except Exception:
        logger.exception(
            "知识变更通知发送失败（不阻塞主流程）：document_id=%s",
            document_id,
        )
        return None
