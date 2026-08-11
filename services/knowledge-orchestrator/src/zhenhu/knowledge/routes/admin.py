"""知识管理 API 端点 —— 入库任务、运行时重置与审计。

GET  /knowledge/import-jobs   — 入库任务列表
POST /knowledge/runtime/reset — 恢复预置样例
GET  /knowledge/audit         — 审计事件列表
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.audit import record_audit_log
from zhenhu.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionJob,
    KnowledgeLifecycleEvent,
    get_session,
)
from zhenhu.knowledge.schemas import (
    AuditListResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    LifecycleEventResponse,
    ResetResponse,
    UnifiedResponse,
)
from zhenhu.knowledge.state_machine import KnowledgeStateMachine

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


# ============================================================================
# 预置样例
# ============================================================================

_SAMPLES = [
    {
        "document_id": "drug-label-amoxicillin-clavulanate",
        "title": "阿莫西林/克拉维酸钾药品说明书（模拟）",
        "version": "2025.01",
        "owner": "药学部（模拟）",
        "status": "published",
        "effective_from": "2025-01-01",
        "effective_until": "2027-01-01",
        "source_format": "txt",
        "chunks": [
            "对青霉素类药物有过敏史者，应由具备处方责任的医师评估。",
        ],
    },
    {
        "document_id": "drug-label-furosemide",
        "title": "呋塞米药品说明书（模拟）",
        "version": "2025.01",
        "owner": "药学部（模拟）",
        "status": "published",
        "effective_from": "2025-01-01",
        "effective_until": "2027-01-01",
        "source_format": "txt",
        "chunks": [
            "呋塞米为强效利尿剂，肾功能损伤者需根据肌酐清除率调整剂量。",
            "使用期间应监测血清电解质（钾、钠）及血压变化。",
        ],
    },
    {
        "document_id": "poc-handoff-sop",
        "title": "院内交接 SOP 样例（模拟）",
        "version": "0.1",
        "owner": "医务处（模拟）",
        "status": "published",
        "effective_from": "2026-01-01",
        "effective_until": "2027-01-01",
        "source_format": "md",
        "chunks": [
            "来源信息冲突时，应并列展示并由经治医生完成核实。",
            "交接信息应包含约定的居家监测记录方式。",
            "复查事项和计划时间应在交接草稿中明确记录。",
        ],
    },
]


async def _insert_preset_samples(session: AsyncSession) -> int:
    """插入预置样例知识文档。

    每个样例对应一个已发布（published）的 document，
    并按其 chunks 列表创建对应分块。

    Returns:
        插入的样例文档数量。
    """
    from datetime import datetime, timezone

    sm = KnowledgeStateMachine(session)
    count = 0

    for sample in _SAMPLES:
        # 每个 chunk 用不同的 content_hash 来区分
        full_content = "\n\n".join(sample["chunks"])
        content_hash = f"preset-{sample['document_id']}"

        doc = KnowledgeDocument(
            document_id=sample["document_id"],
            title=sample["title"],
            version=sample["version"],
            owner=sample["owner"],
            status=sample["status"],
            effective_from=datetime.fromisoformat(sample["effective_from"]).replace(
                tzinfo=timezone.utc
            ),
            effective_until=datetime.fromisoformat(sample["effective_until"]).replace(
                tzinfo=timezone.utc
            ),
            source_format=sample["source_format"],
            source_mime="text/plain",
            source_byte_length=len(full_content.encode("utf-8")),
            content_hash=content_hash,
        )
        session.add(doc)

        for i, chunk_text in enumerate(sample["chunks"]):
            chunk = KnowledgeChunk(
                document_id=sample["document_id"],
                location=f"预置样例 · 第{i + 1}段",
                text=chunk_text,
                chunking_version="0.2.0",
            )
            session.add(chunk)

        await sm.record_import_event(
            document_id=sample["document_id"],
            actor="knowledge_admin",
            detail=f"预置样例恢复：{sample['title']} v{sample['version']}",
        )

        count += 1

    return count


# ============================================================================
# 端点
# ============================================================================


@router.get("/import-jobs")
async def list_import_jobs(
    request: Request,
    status: str | None = Query(default=None, description="按状态过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[IngestionJobListResponse]:
    """列出全部入库任务，支持按状态过滤和分页。"""
    request_id = get_request_id(request)

    from sqlalchemy import select as _select, func as _func

    # 计数
    count_stmt = _select(_func.count(KnowledgeIngestionJob.id))
    if status:
        count_stmt = count_stmt.where(KnowledgeIngestionJob.status == status)
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # 分页查询
    stmt = (
        _select(KnowledgeIngestionJob)
        .order_by(KnowledgeIngestionJob.completed_at.desc().nullsfirst())
    )
    if status:
        stmt = stmt.where(KnowledgeIngestionJob.status == status)
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await session.execute(stmt)
    jobs = result.scalars().all()

    items = [
        IngestionJobResponse(
            job_id=job.job_id,
            status=job.status,
            attempt=job.attempt,
            document_id=job.document_id,
            input_title=job.input_title,
            input_version=job.input_version,
            input_owner=job.input_owner,
            source_file_name=job.source_file_name,
            error_code=job.error_code,
            error_message=job.error_message,
            error_retryable=job.error_retryable,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]

    data = IngestionJobListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.post("/runtime/reset")
async def reset_runtime(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[ResetResponse]:
    """恢复预置样例知识文档。

    删除所有现有文档、分块、入库任务数据（保留审计事件），
    然后重新插入 3 份预置样例。
    """
    request_id = get_request_id(request)

    # 删除所有运行时数据（保留 lifecycle_events 审计记录）
    from sqlalchemy import delete as _delete, func as _func, select as _select
    before_doc_count = (
        await session.execute(_select(_func.count(KnowledgeDocument.id)))
    ).scalar_one()
    await session.execute(_delete(KnowledgeChunk))
    await session.execute(_delete(KnowledgeIngestionJob))
    await session.execute(_delete(KnowledgeDocument))
    await session.flush()

    # 审计：文档删除（运行时重置，记录删除数量）
    await record_audit_log(
        session,
        action_type="knowledge_deleted",
        actor="knowledge_admin",
        resource_type="knowledge",
        detail={"operation": "runtime_reset", "deleted_document_count": before_doc_count},
        request_id=request_id,
    )

    # 插入预置样例
    count = await _insert_preset_samples(session)

    await session.commit()

    data = ResetResponse(status="reset", sample_count=count)
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.get("/audit")
async def list_audit_events(
    request: Request,
    document_id: str | None = Query(default=None, description="按文档 ID 过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[AuditListResponse]:
    """列出知识生命周期审计事件，支持按文档 ID 过滤和分页。

    Returns:
        分页审计事件列表（按发生时间倒序）。
    """
    request_id = get_request_id(request)

    from sqlalchemy import select as _select, func as _func

    # 计数
    count_stmt = _select(_func.count(KnowledgeLifecycleEvent.id))
    if document_id:
        count_stmt = count_stmt.where(
            KnowledgeLifecycleEvent.document_id == document_id
        )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # 分页查询
    stmt = _select(KnowledgeLifecycleEvent).order_by(
        KnowledgeLifecycleEvent.occurred_at.desc()
    )
    if document_id:
        stmt = stmt.where(KnowledgeLifecycleEvent.document_id == document_id)
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await session.execute(stmt)
    events = result.scalars().all()

    items = [
        LifecycleEventResponse(
            audit_id=event.audit_id,
            document_id=event.document_id,
            event_type=event.event_type,
            actor=event.actor,
            detail=event.detail,
            before_state=event.before_state,
            after_state=event.after_state,
            occurred_at=event.occurred_at,
        )
        for event in events
    ]

    data = AuditListResponse(items=items, total=total, page=page, size=size)
    return UnifiedResponse(request_id=request_id, data=data, error=None)
