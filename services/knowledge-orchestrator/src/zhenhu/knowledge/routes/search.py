"""知识检索 API 端点。

GET /knowledge/search?q=关键词 — 混合检索已发布的知识分块。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import get_session
from zhenhu.knowledge.retrieval import fulltext_search
from zhenhu.knowledge.schemas import SearchResponse, SearchResultItem, UnifiedResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


@router.get("/search")
async def search_knowledge(
    request: Request,
    q: str = Query(default="", description="检索关键词"),
    top_k: int = Query(default=10, ge=1, le=50, description="返回结果上限"),
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[SearchResponse]:
    """混合检索知识库。

    在已发布（published）文档的分块中进行全文 LIKE 搜索。
    同时匹配标题和正文，合并去重后按相关度评分降序排列。

    要求 q 参数非空，否则返回 400。
    """
    request_id = get_request_id(request)

    if not q.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "请输入检索关键词",
                "details": {},
            },
        )

    results = await fulltext_search(session, q, top_k=top_k)

    items = [
        SearchResultItem(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            text=item["text"][:500],
            score=item["score"],
            location=item.get("location"),
            citation=item.get("citation", {}),
        )
        for item in results
    ]

    data = SearchResponse(results=items)
    return UnifiedResponse(request_id=request_id, data=data, error=None)
