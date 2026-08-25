"""混合检索模块 —— MySQL LIKE + 模拟向量检索。

阶段 0 使用 MySQL LIKE 进行全文搜索，向量检索预留接口。
搜索结果返回按相关度评分排序的分块引用。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import KnowledgeChunk, KnowledgeDocument


async def search_chunks(
    session: AsyncSession,
    query: str,
    top_k: int = 10,
    status_filter: str | None = "published",
    layers: list[str] | None = None,
    disease_id: str | None = None,
    department: str | None = None,
    as_of: datetime | None = None,
) -> list[dict]:
    """混合检索知识分块。

    使用 SQL LIKE 在已发布分块中进行全文匹配。
    搜索结果按匹配命中次数降序排列，前 top_k 条。

    Args:
        session: 异步数据库会话。
        query: 检索关键词（中文/英文均可）。
        top_k: 返回结果上限。
        status_filter: 文档状态过滤（None 表示不过滤）。

    Returns:
        检索结果列表，每条包含 chunk_id, document_id, text, score, location, citation。
    """
    if not query.strip():
        return []

    # 构建 LIKE 模式：每个字符
    like_pattern = f"%{query}%"

    stmt = (
        select(
            KnowledgeChunk.chunk_id,
            KnowledgeChunk.document_id,
            KnowledgeChunk.text,
            KnowledgeChunk.location,
            KnowledgeDocument.title,
            KnowledgeDocument.version,
            KnowledgeDocument.status,
            KnowledgeDocument.layer,
            KnowledgeDocument.disease_id,
            KnowledgeDocument.department,
            KnowledgeDocument.source_type,
            KnowledgeDocument.evidence_level,
            KnowledgeDocument.guideline_year,
            KnowledgeDocument.source_credibility,
            KnowledgeDocument.evidence_metadata_origin,
            KnowledgeDocument.effective_from,
            KnowledgeDocument.effective_until,
        )
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.document_id)
        .where(
            KnowledgeChunk.text.like(like_pattern),
        )
    )

    if status_filter:
        stmt = stmt.where(KnowledgeDocument.status == status_filter)
    stmt = _apply_scope_filters(stmt, layers=layers, disease_id=disease_id, department=department, as_of=as_of)

    stmt = stmt.order_by(func.length(KnowledgeChunk.text).asc()).limit(top_k)

    result = await session.execute(stmt)
    rows = result.all()

    results = []
    for i, row in enumerate(rows):
        # 简单相关度评分：匹配命中次数 / 总字符数 * 位置衰减
        hit_count = row.text.count(query)
        score = min(1.0, max(0.1, hit_count / max(1, len(row.text)) * 100 + 0.1))
        # 排名靠前给更高的分值衰减
        score = round(score * (1.0 - i * 0.05), 4)

        results.append({
            "chunk_id": row.chunk_id,
            "document_id": row.document_id,
            "text": row.text,
            "score": score,
            "location": row.location or "未知位置",
            "citation": {
                "excerpt": row.text[:200] if row.text else "",
                "coordinates": row.location or "未知位置",
                "document_title": row.title,
                "document_version": row.version,
                "document_status": row.status,
                "layer": row.layer,
                "disease_id": row.disease_id,
                "department": row.department,
                "source_type": row.source_type,
                "evidence_level": row.evidence_level,
                "guideline_year": row.guideline_year,
                "source_credibility": row.source_credibility,
                "evidence_metadata_origin": row.evidence_metadata_origin,
                "effective_from": row.effective_from.isoformat() if row.effective_from else None,
                "effective_until": row.effective_until.isoformat() if row.effective_until else None,
                "retrieval_strategy_version": "poc-hybrid-stage0-0.1",
            },
        })

    # 按评分降序
    results.sort(key=lambda x: (x["score"], x["citation"].get("source_credibility", 0.5)), reverse=True)
    return _annotate_evidence_conflicts(results)


async def fulltext_search(
    session: AsyncSession,
    query: str,
    top_k: int = 10,
    layers: list[str] | None = None,
    disease_id: str | None = None,
    department: str | None = None,
    as_of: datetime | None = None,
) -> list[dict]:
    """扩展搜索 —— 同时检索标题和正文。

    除了 chunk text 的 LIKE 匹配，还加入 document title 的匹配。
    合并结果后去重、排序。

    Args:
        session: 异步数据库会话。
        query: 检索关键词。
        top_k: 返回结果上限。

    Returns:
        合并后的搜索结果列表。
    """
    if not query.strip():
        return []

    like_pattern = f"%{query}%"

    # 标题匹配的文档
    title_stmt = (
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.title.like(like_pattern),
            KnowledgeDocument.status == "published",
        )
        .limit(top_k)
    )
    title_stmt = _apply_scope_filters(title_stmt, layers=layers, disease_id=disease_id, department=department, as_of=as_of)
    title_result = await session.execute(title_stmt)
    title_docs = title_result.scalars().all()

    # 子查询：标题匹配文档下的所有分块
    title_doc_ids = [d.document_id for d in title_docs]
    extra_results = []
    if title_doc_ids:
        chunk_stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.document_id)
            .where(KnowledgeChunk.document_id.in_(title_doc_ids))
            .limit(top_k * 5)
        )
        chunk_result = await session.execute(chunk_stmt)
        for chunk, document in chunk_result.all():
            extra_results.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "score": 0.3,
                "location": chunk.location or "未知位置",
                "citation": {
                    "excerpt": chunk.text[:200] if chunk.text else "",
                    "coordinates": chunk.location or "未知位置",
                    "document_title": document.title,
                    "document_version": document.version,
                    "document_status": document.status,
                    "layer": document.layer,
                    "disease_id": document.disease_id,
                    "department": document.department,
                    "source_type": document.source_type,
                    "evidence_level": document.evidence_level,
                    "guideline_year": document.guideline_year,
                    "source_credibility": document.source_credibility,
                    "evidence_metadata_origin": document.evidence_metadata_origin,
                    "effective_from": document.effective_from.isoformat() if document.effective_from else None,
                    "effective_until": document.effective_until.isoformat() if document.effective_until else None,
                    "retrieval_strategy_version": "poc-title-match-0.1",
                },
            })

    # 正文匹配
    text_results = await search_chunks(
        session,
        query,
        top_k=top_k,
        layers=layers,
        disease_id=disease_id,
        department=department,
        as_of=as_of,
    )

    # 合并去重（按 chunk_id）
    seen = set()
    merged = []
    for item in text_results + extra_results:
        if item["chunk_id"] not in seen:
            seen.add(item["chunk_id"])
            merged.append(item)

    merged.sort(key=lambda x: (x["score"], x["citation"].get("source_credibility", 0.5)), reverse=True)
    return _annotate_evidence_conflicts(merged[:top_k])


def parse_layers(value: str | None) -> list[str] | None:
    layers = [item.strip() for item in (value or "").split(",") if item.strip()]
    return layers or None


def parse_as_of(value: str | None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _apply_scope_filters(stmt, *, layers: list[str] | None, disease_id: str | None, department: str | None, as_of: datetime | None):
    effective_at = as_of or datetime.now(timezone.utc)
    stmt = stmt.where(
        (KnowledgeDocument.effective_from.is_(None)) | (KnowledgeDocument.effective_from <= effective_at),
        (KnowledgeDocument.effective_until.is_(None)) | (KnowledgeDocument.effective_until >= effective_at),
    )
    if layers:
        stmt = stmt.where(KnowledgeDocument.layer.in_(layers))
    if disease_id:
        stmt = stmt.where((KnowledgeDocument.disease_id == disease_id) | (KnowledgeDocument.disease_id.is_(None)) | (KnowledgeDocument.disease_id == ""))
    if department:
        stmt = stmt.where((KnowledgeDocument.department == department) | (KnowledgeDocument.department.is_(None)) | (KnowledgeDocument.department == ""))
    return stmt


def _annotate_evidence_conflicts(results: list[dict]) -> list[dict]:
    """Flag only explicit directional disagreement across same-disease sources."""
    by_disease: dict[str, list[dict]] = {}
    for item in results:
        disease_id = str(item["citation"].get("disease_id") or "").strip()
        if disease_id:
            by_disease.setdefault(disease_id, []).append(item)
    negative = ("不建议", "不推荐", "不应", "避免")
    for disease_id, items in by_disease.items():
        if len({item["document_id"] for item in items}) < 2:
            continue
        has_positive = any(
            any(term in item["text"] for term in ("建议", "推荐", "可考虑", "应当"))
            and not any(term in item["text"] for term in negative)
            for item in items
        )
        has_negative = any(any(term in item["text"] for term in negative) for item in items)
        if not (has_positive and has_negative):
            continue
        for item in items:
            citation = item["citation"]
            citation["conflict_detected"] = True
            citation["conflict_group"] = f"disease:{disease_id}"
            citation["conflict_note"] = "同病种检索结果存在方向性表述差异，需由临床人员核验来源、年份和适用范围。"
    return results
