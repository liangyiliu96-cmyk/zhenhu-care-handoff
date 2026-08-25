"""知识检索 API 端点。

GET /knowledge/search?q=关键词 — 混合检索已发布的知识分块。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.audit import record_audit_log
from zhenhu.knowledge.models import get_session
from zhenhu.knowledge.retrieval import fulltext_search, parse_as_of, parse_layers
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
    layers: str | None = Query(default=None, description="逗号分隔的知识层级，如 L5,L11"),
    disease_id: str | None = Query(default=None, description="病种 ID"),
    department: str | None = Query(default=None, description="科室"),
    as_of: str | None = Query(default=None, description="知识生效日期/时间，默认当前时间"),
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

    scoped_layers = parse_layers(layers)
    try:
        effective_at = parse_as_of(as_of)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "as_of 不是合法的 ISO 日期或时间",
                "details": {"as_of": as_of},
            },
        ) from exc
    results = await fulltext_search(
        session,
        q,
        top_k=top_k,
        layers=scoped_layers,
        disease_id=disease_id,
        department=department,
        as_of=effective_at,
    )

    # 审计：检索操作（不可变证据链，记录 query / top_k / 命中数）
    actor = request.headers.get("X-User-Role", "system")
    await record_audit_log(
        session,
        action_type="knowledge_search",
        actor=actor,
        resource_type="knowledge",
        detail={
            "query": q,
            "top_k": top_k,
            "layers": scoped_layers or [],
            "disease_id": disease_id or "",
            "department": department or "",
            "as_of": effective_at.isoformat(),
            "result_count": len(results),
        },
        request_id=request_id,
    )
    await session.commit()

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

    source_types = sorted({str(item.get("citation", {}).get("source_type") or "unknown") for item in results})
    evidence_levels = sorted({str(item.get("citation", {}).get("evidence_level") or "unknown") for item in results})
    guideline_years = sorted({item.get("citation", {}).get("guideline_year") for item in results if item.get("citation", {}).get("guideline_year")}, reverse=True)
    conflict_groups = sorted({str(item.get("citation", {}).get("conflict_group")) for item in results if item.get("citation", {}).get("conflict_detected")})
    data = SearchResponse(results=items, evidence_summary={
        "source_types": source_types,
        "evidence_levels": evidence_levels,
        "guideline_years": guideline_years,
        "conflict_detected": bool(conflict_groups),
        "conflict_groups": conflict_groups,
        "result_count": len(results),
    })
    return UnifiedResponse(request_id=request_id, data=data, error=None)
