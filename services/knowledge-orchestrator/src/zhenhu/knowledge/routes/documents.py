"""知识文档相关 API 端点。

POST /knowledge/documents/import  — 导入知识文档
GET  /knowledge/documents         — 列出全部文档
POST /knowledge/documents/{id}/transition — 状态转移
"""

from __future__ import annotations

import hashlib
import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionJob,
    get_session,
    _utcnow,
)
from zhenhu.knowledge.schemas import (
    DocumentImportResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentTransitionRequest,
    DocumentTransitionResponse,
    ImportDocumentRequest,
    UnifiedResponse,
)
from zhenhu.knowledge.state_machine import KnowledgeStateMachine, StateMachineError
from zhenhu.knowledge.hooks import notify_knowledge_changed
from zhenhu.knowledge.scope_policy import infer_knowledge_scope, infer_evidence_metadata
from zhenhu.contracts import KNOWLEDGE_TERMINAL_STATES
from zhenhu.contracts.agent import get_ai_provider, AgentAuditHook  # 阶段M Agent升级

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ============================================================================
# 依赖注入
# ============================================================================


def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


# ============================================================================
# 分块工具
# ============================================================================


def _chunk_text(content: str, max_length: int = 420) -> list[str]:
    """将文档按段落分块，保证每块长度不超过 max_length。

    Args:
        content: 文档正文。
        max_length: 每块最大字符数。

    Returns:
        文本块列表。
    """
    paragraphs = content.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n\n")
    chunks = []
    buffer = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 如果单段过长，按句子切分
        if len(para) > max_length:
            sentences = para.replace("。", "。|").replace("；", "；|").split("|")
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                while len(sentence) > max_length:
                    if buffer:
                        chunks.append(buffer)
                        buffer = ""
                    chunks.append(sentence[:max_length])
                    sentence = sentence[max_length:]
                if buffer and len(buffer) + len(sentence) + 1 > max_length:
                    chunks.append(buffer)
                    buffer = ""
                buffer = f"{buffer}\n{sentence}" if buffer else sentence
        else:
            if buffer and len(buffer) + len(para) + 1 > max_length:
                chunks.append(buffer)
                buffer = ""
            buffer = f"{buffer}\n{para}" if buffer else para
    if buffer:
        chunks.append(buffer)
    return chunks


# ============================================================================
# 端点
# ============================================================================


@router.post("/documents/import", status_code=201)
async def import_document(
    body: ImportDocumentRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[DocumentImportResponse]:
    """导入知识文档。

    将正文按段落分块后创建 document(review_pending) 和对应的入库任务。
    内容去重：若已存在相同 content_hash 的文档，拒绝导入。

    状态码 201：导入成功，文档进入待审核。
    """
    request_id = get_request_id(request)

    # 计算内容摘要
    content_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()

    # 去重检查
    from sqlalchemy import select as _select
    dup_result = await session.execute(
        _select(KnowledgeDocument).where(
            KnowledgeDocument.content_hash == content_hash
        )
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_KNOWLEDGE_CONTENT",
                "message": "相同内容已存在于知识资产中",
                "details": {"content_hash": content_hash},
            },
        )

    scope = infer_knowledge_scope(
        title=body.title,
        owner=body.owner,
        content=body.content,
        layer=body.layer,
        disease_id=body.disease_id,
        department=body.department,
    )
    evidence_metadata = infer_evidence_metadata(
        title=body.title,
        owner=body.owner,
        content=body.content,
        source_type=body.source_type,
        evidence_level=body.evidence_level,
        guideline_year=body.guideline_year,
    )

    # 创建文档
    from datetime import datetime, timezone
    effective_from = datetime.fromisoformat(body.effective_from).replace(
        tzinfo=timezone.utc
    )
    effective_until = datetime.fromisoformat(body.effective_until).replace(
        tzinfo=timezone.utc
    )

    document = KnowledgeDocument(
        title=body.title,
        version=body.version,
        owner=body.owner,
        layer=scope["layer"],
        disease_id=scope["disease_id"],
        department=scope["department"],
        **evidence_metadata,
        status="review_pending",
        effective_from=effective_from,
        effective_until=effective_until,
        source_format=body.source_format,
        source_mime="text/plain" if body.source_format == "txt" else "text/markdown",
        source_byte_length=len(body.content.encode("utf-8")),
        content_hash=content_hash,
    )
    session.add(document)
    await session.flush()

    # 分块
    chunks = _chunk_text(body.content)
    new_chunks = []
    for i, chunk_text in enumerate(chunks):
        chunk = KnowledgeChunk(
            document_id=document.document_id,
            location=f"第{i + 1}段",
            text=chunk_text,
            chunking_version="0.2.0",
        )
        session.add(chunk)
        new_chunks.append(chunk)

    # 阶段5: LLM 自动提取标签（失败回退默认标签）
    audit = AgentAuditHook()
    audit.on_node_enter("import", {"source_format": body.source_format})
    try:
        provider = get_ai_provider()
        tag_result = await provider.invoke(
            "从以下文本提取3-5个医学关键词和1-2个疾病分类标签。返回JSON: {keywords:[...], disease_tags:[...]}",
            context={"chunks": [{"id": c.chunk_id, "text": (c.text or "")[:500]} for c in new_chunks]},
        )
        if tag_result and tag_result.get("source_type") != "source_none":
            keywords = tag_result.get("keywords", [])
            disease_tags = tag_result.get("disease_tags", ["综合"])
        else:
            keywords, disease_tags = [], ["综合"]
    except Exception:
        keywords, disease_tags = [], ["综合"]

    # 用 AI 返回的标签更新分块元数据
    for chunk in new_chunks:
        chunk.tags = _json.dumps(disease_tags[:2], ensure_ascii=False) if disease_tags else "[]"
        chunk.keywords = _json.dumps(keywords[:5], ensure_ascii=False) if keywords else "[]"
    audit.on_node_exit("import", {"chunk_count": len(new_chunks)})

    # 记录入库任务
    job = KnowledgeIngestionJob(
        status="review_pending",
        attempt=1,
        document_id=document.document_id,
        input_title=body.title,
        input_version=body.version,
        input_owner=body.owner,
        source_file_name=f"{body.title}.{body.source_format}",
        started_at=_utcnow(),
        completed_at=_utcnow(),
    )
    session.add(job)

    # 记录生命周期事件
    sm = KnowledgeStateMachine(session)
    await sm.record_import_event(
        document_id=document.document_id,
        actor="knowledge_admin",
        detail=f"导入 {body.title} v{body.version}，生成 {len(chunks)} 个分块，等待发布审核",
    )

    await session.commit()

    data = DocumentImportResponse(
        job_id=job.job_id,
        status="review_pending",
    )
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.get("/documents")
async def list_documents(
    request: Request,
    status: str | None = Query(default=None, description="按状态过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[DocumentListResponse]:
    """列出全部知识文档，支持按状态过滤和分页。

    可选的 ?status=published 过滤已发布的文档。
    返回分页对象：items + total + page + size。
    """
    request_id = get_request_id(request)

    from sqlalchemy import select as _select, func as _func

    # 计数
    count_stmt = _select(_func.count(KnowledgeDocument.id))
    if status:
        count_stmt = count_stmt.where(KnowledgeDocument.status == status)
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # 分页查询
    stmt = _select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if status:
        stmt = stmt.where(KnowledgeDocument.status == status)
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await session.execute(stmt)
    docs = result.scalars().all()

    items = []
    for doc in docs:
        # 计算分块数量
        chunk_count_stmt = _select(_func.count(KnowledgeChunk.id)).where(
            KnowledgeChunk.document_id == doc.document_id
        )
        chunk_count_result = await session.execute(chunk_count_stmt)
        chunk_count = chunk_count_result.scalar_one()

        items.append(
            DocumentResponse(
                document_id=doc.document_id,
                title=doc.title,
                version=doc.version,
                status=doc.status,
                owner=doc.owner,
                layer=doc.layer,
                disease_id=doc.disease_id,
                department=doc.department,
                source_type=doc.source_type,
                evidence_level=doc.evidence_level,
                guideline_year=doc.guideline_year,
                source_credibility=doc.source_credibility,
                evidence_metadata_origin=doc.evidence_metadata_origin,
                effective_from=doc.effective_from.isoformat()[:10] if doc.effective_from else None,
                effective_until=doc.effective_until.isoformat()[:10] if doc.effective_until else None,
                source_format=doc.source_format,
                chunk_count=chunk_count,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )

    data = DocumentListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.post("/documents/{document_id}/transition")
async def transition_document(
    document_id: str,
    body: DocumentTransitionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[DocumentTransitionResponse]:
    """执行知识文档状态转移。

    调用 KnowledgeStateMachine.transition() 完成转移，
    校验通过后写入 lifecycle_event 审计记录。
    若转移到终态（撤回/过期/替代/归档），异步通知 workflow-engine。
    """
    request_id = get_request_id(request)
    sm = KnowledgeStateMachine(session)

    from sqlalchemy import select as _select
    result = await session.execute(
        _select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": f"知识文档不存在：{document_id}",
                "details": {"document_id": document_id},
            },
        )

    try:
        await sm.transition(
            document=doc,
            next_state=body.next_state,
            actor="knowledge_admin",
            reason=f"手工触发状态转移：{doc.status} → {body.next_state}",
        )
    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc

    await session.commit()

    # 终态通知：若知识进入终态，异步通知工作流引擎阻断受影响的病例
    if body.next_state in {s.value for s in KNOWLEDGE_TERMINAL_STATES}:
        await notify_knowledge_changed(
            document_id=doc.document_id,
            version=doc.version,
            actor="knowledge_admin",
        )

    data = DocumentTransitionResponse(
        document_id=doc.document_id,
        status=doc.status,
    )
    return UnifiedResponse(request_id=request_id, data=data, error=None)
