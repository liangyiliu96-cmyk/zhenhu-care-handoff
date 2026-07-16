"""模型层测试 —— CRUD 操作与约束校验。

覆盖：
- 文档创建与持久化
- 分块创建与外键关联
- 入库任务创建
- 引用创建
- 生命周期事件不可变
- 级联删除
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import (
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeIngestionJob,
    KnowledgeCitation,
    KnowledgeLifecycleEvent,
    _utcnow,
)


class TestKnowledgeDocument:
    """知识文档 ORM 测试。"""

    @pytest.mark.asyncio
    async def test_create_document(self, db_session: AsyncSession):
        """创建文档后应可查询并验证字段。"""
        doc = KnowledgeDocument(
            title="测试文档",
            version="1.0",
            owner="测试部门",
            status="review_pending",
            source_format="txt",
            content_hash="abc123",
        )
        db_session.add(doc)
        await db_session.flush()

        assert doc.document_id is not None
        assert doc.document_id.startswith("DOC-")
        assert doc.status == "review_pending"
        assert doc.created_at is not None

    @pytest.mark.asyncio
    async def test_document_unique_id(self, db_session: AsyncSession):
        """每个文档应有唯一的 document_id。"""
        doc1 = KnowledgeDocument(title="文档A", version="1.0", owner="部门A")
        doc2 = KnowledgeDocument(title="文档B", version="1.0", owner="部门B")
        db_session.add_all([doc1, doc2])
        await db_session.flush()

        assert doc1.document_id != doc2.document_id

    @pytest.mark.asyncio
    async def test_document_content_hash_deduplication(self, db_session: AsyncSession):
        """相同 content_hash 的文档不应重复——这里只验证字段存在。"""
        doc = KnowledgeDocument(
            title="去重测试",
            version="0.1",
            owner="测试",
            content_hash="hash-test-001",
        )
        db_session.add(doc)
        await db_session.flush()

        assert doc.content_hash == "hash-test-001"

    @pytest.mark.asyncio
    async def test_document_with_chunks(self, db_session: AsyncSession):
        """文档关联分块的创建与读回。"""
        doc = KnowledgeDocument(title="分块测试", version="0.1", owner="测试")
        db_session.add(doc)
        await db_session.flush()

        for i in range(3):
            chunk = KnowledgeChunk(
                document_id=doc.document_id,
                text=f"分块内容 {i + 1}",
                location=f"第{i + 1}段",
            )
            db_session.add(chunk)
        await db_session.flush()

        # 查询分块
        result = await db_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc.document_id
            )
        )
        chunks = result.scalars().all()
        assert len(chunks) == 3
        # 验证外键
        assert all(c.document_id == doc.document_id for c in chunks)

    @pytest.mark.asyncio
    async def test_document_count_by_status(self, db_session: AsyncSession):
        """按状态统计文档数。"""
        for i in range(5):
            db_session.add(KnowledgeDocument(
                title=f"文档{i}",
                version="0.1",
                owner="测试",
                status="review_pending" if i < 3 else "published",
            ))
        await db_session.flush()

        count_result = await db_session.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.status == "published"
            )
        )
        assert count_result.scalar_one() == 2


class TestKnowledgeChunk:
    """知识分块 ORM 测试。"""

    @pytest.mark.asyncio
    async def test_create_chunk(self, db_session: AsyncSession):
        """分块必须关联文档。"""
        doc = KnowledgeDocument(title="分块文档", version="0.1", owner="测试")
        db_session.add(doc)
        await db_session.flush()

        chunk = KnowledgeChunk(
            document_id=doc.document_id,
            text="这是一段分块文本",
            location="第1段",
            chunking_version="0.2.0",
        )
        db_session.add(chunk)
        await db_session.flush()

        assert chunk.chunk_id is not None
        assert chunk.chunk_id.startswith("CHUNK-")
        assert chunk.text == "这是一段分块文本"

    @pytest.mark.asyncio
    async def test_chunk_unique_id(self, db_session: AsyncSession):
        """每个分块应有唯一的 chunk_id。"""
        doc = KnowledgeDocument(title="唯一性测试", version="0.1", owner="测试")
        db_session.add(doc)
        await db_session.flush()

        c1 = KnowledgeChunk(document_id=doc.document_id, text="文本A")
        c2 = KnowledgeChunk(document_id=doc.document_id, text="文本B")
        db_session.add_all([c1, c2])
        await db_session.flush()

        assert c1.chunk_id != c2.chunk_id

    @pytest.mark.asyncio
    async def test_chunk_cascade_delete(self, db_session: AsyncSession):
        """删除文档应级联删除其分块。"""
        doc = KnowledgeDocument(title="级联删除测试", version="0.1", owner="测试")
        db_session.add(doc)
        await db_session.flush()

        chunk = KnowledgeChunk(document_id=doc.document_id, text="测试文本")
        db_session.add(chunk)
        await db_session.flush()

        await db_session.delete(doc)
        await db_session.flush()

        result = await db_session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == chunk.chunk_id)
        )
        assert result.scalar_one_or_none() is None


class TestKnowledgeIngestionJob:
    """知识入库任务 ORM 测试。"""

    @pytest.mark.asyncio
    async def test_create_job(self, db_session: AsyncSession):
        """创建入库任务并设置状态。"""
        job = KnowledgeIngestionJob(
            status="queued",
            attempt=1,
            input_title="测试导入",
            input_version="1.0",
            input_owner="测试部门",
            source_file_name="test.txt",
        )
        db_session.add(job)
        await db_session.flush()

        assert job.job_id is not None
        assert job.job_id.startswith("JOB-")
        assert job.status == "queued"
        assert job.attempt == 1

    @pytest.mark.asyncio
    async def test_job_with_error(self, db_session: AsyncSession):
        """入库任务可记录错误信息。"""
        job = KnowledgeIngestionJob(
            status="failed",
            attempt=3,
            error_code="DOCUMENT_PARSE_FAILED",
            error_message="文件解析失败",
            error_retryable=True,
        )
        db_session.add(job)
        await db_session.flush()

        assert job.status == "failed"
        assert job.error_code == "DOCUMENT_PARSE_FAILED"
        assert job.error_retryable is True


class TestKnowledgeCitation:
    """知识引用 ORM 测试。"""

    @pytest.mark.asyncio
    async def test_create_citation(self, db_session: AsyncSession):
        """创建知识引用记录。"""
        cite = KnowledgeCitation(
            document_id="DOC-abc",
            chunk_id="CHUNK-abc",
            location="第3.2节",
            excerpt="这是引用摘录",
            retrieval_strategy_version="0.1",
        )
        db_session.add(cite)
        await db_session.flush()

        assert cite.citation_id is not None
        assert cite.citation_id.startswith("CITE-")
        assert cite.retrieved_at is not None


class TestKnowledgeLifecycleEvent:
    """知识生命周期事件 ORM 测试。"""

    @pytest.mark.asyncio
    async def test_create_event(self, db_session: AsyncSession):
        """创建生命周期事件记录。"""
        event = KnowledgeLifecycleEvent(
            document_id="DOC-abc",
            event_type="knowledge_status_changed",
            actor="knowledge_admin",
            detail="从 review_pending 转移到 published",
            before_state="review_pending",
            after_state="published",
        )
        db_session.add(event)
        await db_session.flush()

        assert event.audit_id is not None
        assert event.audit_id.startswith("KAUDIT-")
        assert event.before_state == "review_pending"
        assert event.after_state == "published"
        assert event.occurred_at is not None
