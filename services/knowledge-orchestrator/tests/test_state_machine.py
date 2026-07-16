"""知识版本状态机核心测试。

覆盖：
- 合法转移（≥6 条）
- 非法转移（≥4 条）
- 生命周期事件写入
- 状态机错误包含正确错误码
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.knowledge.models import KnowledgeDocument, KnowledgeLifecycleEvent
from zhenhu.knowledge.state_machine import KnowledgeStateMachine, StateMachineError


class TestKnowledgeStateMachine:
    """知识文档状态机测试。"""

    @pytest.fixture
    async def published_doc(self, db_session: AsyncSession) -> KnowledgeDocument:
        """创建一个已发布的测试文档。"""
        doc = KnowledgeDocument(
            title="状态机测试文档", version="0.1", owner="测试部门",
            status="published", content_hash="sm-test-001",
        )
        db_session.add(doc)
        await db_session.flush()
        return doc

    @pytest.fixture
    async def pending_doc(self, db_session: AsyncSession) -> KnowledgeDocument:
        """创建一个待审核的测试文档。"""
        doc = KnowledgeDocument(
            title="待审核文档", version="0.1", owner="测试部门",
            status="review_pending", content_hash="sm-pending-001",
        )
        db_session.add(doc)
        await db_session.flush()
        return doc

    # =========================================================================
    # 合法转移
    # =========================================================================

    @pytest.mark.asyncio
    async def test_review_pending_to_published(self, db_session: AsyncSession, pending_doc):
        """review_pending → published 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(pending_doc, "published", actor="knowledge_admin")
        assert pending_doc.status == "published"

    @pytest.mark.asyncio
    async def test_review_pending_to_withdrawn(self, db_session: AsyncSession, pending_doc):
        """review_pending → withdrawn 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(pending_doc, "withdrawn", actor="knowledge_admin")
        assert pending_doc.status == "withdrawn"

    @pytest.mark.asyncio
    async def test_review_pending_to_review_rejected(self, db_session: AsyncSession, pending_doc):
        """review_pending → review_rejected 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(pending_doc, "review_rejected", actor="knowledge_admin")
        assert pending_doc.status == "review_rejected"

    @pytest.mark.asyncio
    async def test_published_to_expired(self, db_session: AsyncSession, published_doc):
        """published → expired 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(published_doc, "expired", actor="knowledge_admin")
        assert published_doc.status == "expired"

    @pytest.mark.asyncio
    async def test_published_to_withdrawn(self, db_session: AsyncSession, published_doc):
        """published → withdrawn 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(published_doc, "withdrawn", actor="knowledge_admin")
        assert published_doc.status == "withdrawn"

    @pytest.mark.asyncio
    async def test_published_to_superseded(self, db_session: AsyncSession, published_doc):
        """published → superseded 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(published_doc, "superseded", actor="knowledge_admin")
        assert published_doc.status == "superseded"

    @pytest.mark.asyncio
    async def test_published_to_archived(self, db_session: AsyncSession, published_doc):
        """published → archived 合法。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(published_doc, "archived", actor="knowledge_admin")
        assert published_doc.status == "archived"

    # =========================================================================
    # 非法转移
    # =========================================================================

    @pytest.mark.asyncio
    async def test_illegal_published_to_review_pending(self, db_session: AsyncSession, published_doc):
        """published → review_pending 非法（不可逆）。"""
        sm = KnowledgeStateMachine(db_session)
        with pytest.raises(StateMachineError) as exc_info:
            await sm.transition(published_doc, "review_pending")
        assert exc_info.value.code == "ILLEGAL_TRANSITION"
        assert published_doc.status == "published"

    @pytest.mark.asyncio
    async def test_illegal_expired_to_published(self, db_session: AsyncSession):
        """终态 expired 不可转移。"""
        doc = KnowledgeDocument(
            title="终态测试", version="0.1", owner="测试",
            status="expired", content_hash="terminal-001",
        )
        db_session.add(doc)
        await db_session.flush()

        sm = KnowledgeStateMachine(db_session)
        with pytest.raises(StateMachineError) as exc_info:
            await sm.transition(doc, "published")
        assert exc_info.value.code == "ILLEGAL_TRANSITION"
        assert doc.status == "expired"

    @pytest.mark.asyncio
    async def test_illegal_review_rejected_to_published(self, db_session: AsyncSession):
        """终态 review_rejected 不可转移。"""
        doc = KnowledgeDocument(
            title="驳回终态", version="0.1", owner="测试",
            status="review_rejected", content_hash="rejected-001",
        )
        db_session.add(doc)
        await db_session.flush()

        sm = KnowledgeStateMachine(db_session)
        with pytest.raises(StateMachineError) as exc_info:
            await sm.transition(doc, "published")
        assert exc_info.value.code == "ILLEGAL_TRANSITION"

    @pytest.mark.asyncio
    async def test_illegal_withdrawn_to_published(self, db_session: AsyncSession):
        """终态 withdrawn 不可转移。"""
        doc = KnowledgeDocument(
            title="撤回终态", version="0.1", owner="测试",
            status="withdrawn", content_hash="withdrawn-001",
        )
        db_session.add(doc)
        await db_session.flush()

        sm = KnowledgeStateMachine(db_session)
        with pytest.raises(StateMachineError) as exc_info:
            await sm.transition(doc, "published")
        assert exc_info.value.code == "ILLEGAL_TRANSITION"

    # =========================================================================
    # 生命周期事件
    # =========================================================================

    @pytest.mark.asyncio
    async def test_lifecycle_event_written_on_transition(self, db_session: AsyncSession, pending_doc):
        """每次合法转移应写入一条生命周期事件。"""
        sm = KnowledgeStateMachine(db_session)
        await sm.transition(pending_doc, "published", actor="knowledge_admin")
        await db_session.flush()

        result = await db_session.execute(
            select(KnowledgeLifecycleEvent).where(
                KnowledgeLifecycleEvent.document_id == pending_doc.document_id
            )
        )
        events = result.scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "knowledge_status_changed"
        assert events[0].before_state == "review_pending"
        assert events[0].after_state == "published"
        assert events[0].actor == "knowledge_admin"

    @pytest.mark.asyncio
    async def test_multiple_transitions_produce_multiple_events(self, db_session: AsyncSession, pending_doc):
        """多次转移应产生多条生命周期事件。"""
        sm = KnowledgeStateMachine(db_session)

        # review_pending → published
        await sm.transition(pending_doc, "published", actor="knowledge_admin")
        # published → expired
        await sm.transition(pending_doc, "expired", actor="knowledge_admin",
                            reason="有效期到期")
        await db_session.flush()

        result = await db_session.execute(
            select(KnowledgeLifecycleEvent).where(
                KnowledgeLifecycleEvent.document_id == pending_doc.document_id
            ).order_by(KnowledgeLifecycleEvent.occurred_at.asc())
        )
        events = result.scalars().all()
        assert len(events) == 2
        assert events[0].after_state == "published"
        assert events[1].after_state == "expired"

    @pytest.mark.asyncio
    async def test_record_import_event(self, db_session: AsyncSession):
        """record_import_event 记录导入事件。"""
        doc = KnowledgeDocument(
            title="导入事件测试", version="0.1", owner="测试",
            status="review_pending", content_hash="import-event-001",
        )
        db_session.add(doc)
        await db_session.flush()

        sm = KnowledgeStateMachine(db_session)
        await sm.record_import_event(
            document_id=doc.document_id,
            actor="knowledge_admin",
            detail="导入测试文档，生成 3 个分块",
        )
        await db_session.flush()

        result = await db_session.execute(
            select(KnowledgeLifecycleEvent).where(
                KnowledgeLifecycleEvent.document_id == doc.document_id
            )
        )
        events = result.scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "knowledge_imported"
        assert events[0].after_state == "review_pending"

    # =========================================================================
    # 错误码
    # =========================================================================

    @pytest.mark.asyncio
    async def test_state_machine_error_contains_code_and_details(self, db_session: AsyncSession, published_doc):
        """StateMachineError 应包含 code 和 details。"""
        sm = KnowledgeStateMachine(db_session)
        try:
            await sm.transition(published_doc, "review_pending")
        except StateMachineError as exc:
            assert exc.code == "ILLEGAL_TRANSITION"
            assert "current_state" in exc.details
            assert exc.details["current_state"] == "published"
            assert exc.details["next_state"] == "review_pending"
