"""Hook 端点 —— 跨服务内部回调。

POST /hooks/knowledge-changed — 知识变更阻断钩子（knowledge-orchestrator 调用）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.workflow.models import get_session
from zhenhu.workflow.schemas import (
    KnowledgeChangedHookRequest,
    KnowledgeChangedHookResponse,
    UnifiedResponse,
)
from zhenhu.workflow.state_machine import CaseStateMachine, StateMachineError

router = APIRouter(prefix="/hooks", tags=["hooks"])


def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


@router.post("/knowledge-changed")
async def knowledge_changed_hook(
    body: KnowledgeChangedHookRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[KnowledgeChangedHookResponse]:
    """知识变更阻断钩子。

    由 knowledge-orchestrator 在知识文档过期/撤回/被替代后调用。
    查找所有 state 为 task_draft 或 review_pending 且引用该 document_id 的病例，
    标记为 knowledge_changed 状态。

    Args:
        body: 包含 document_id。

    Returns:
        包含 blocked_count（受影响病例数量）。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    try:
        result = await sm.on_knowledge_changed(document_id=body.document_id)

        await session.commit()

        data = KnowledgeChangedHookResponse(blocked_count=result["blocked_count"])
        return UnifiedResponse(request_id=request_id, data=data, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc
