"""FastAPI 端点集成测试 —— knowledge-orchestrator 全部 7 端点。

覆盖：
- GET /health
- POST /knowledge/documents/import (201)
- GET /knowledge/documents (200, 支持 ?status=)
- POST /knowledge/documents/{id}/transition (200 / 409 / 404)
- GET /knowledge/search?q= (200 / 400)
- GET /knowledge/import-jobs (200)
- POST /knowledge/runtime/reset (200)
- GET /knowledge/audit (200)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestHealthEndpoint:
    """健康检查端点测试。"""

    @pytest.fixture
    async def client(self):
        """创建 AsyncClient 用于测试 FastAPI app。"""
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        """GET /health 应返回 200 和 service info。"""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_request_id_header(self, client):
        """每个响应应包含 X-Request-ID 头。"""
        resp = await client.get("/health")
        assert "x-request-id" in resp.headers


class TestDocumentImport:
    """知识文档导入端点测试。"""

    @pytest.fixture
    async def client(self):
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_import_document_201(self, client, sample_document_data):
        """POST /knowledge/documents/import 应返回 201。"""
        resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["status"] == "review_pending"
        assert data["data"]["job_id"].startswith("JOB-")

    @pytest.mark.asyncio
    async def test_import_duplicate_409(self, client, sample_document_data):
        """重复导入相同内容应返回 409。"""
        # 第一次导入
        await client.post("/knowledge/documents/import", json=sample_document_data)
        # 第二次导入
        resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        assert resp.status_code == 409
        error = resp.json()["error"]
        assert error["code"] == "DUPLICATE_KNOWLEDGE_CONTENT"

    @pytest.mark.asyncio
    async def test_list_documents_200(self, client, sample_document_data):
        """GET /knowledge/documents 返回所有文档。"""
        # 先导入一个文档
        await client.post("/knowledge/documents/import", json=sample_document_data)

        resp = await client.get("/knowledge/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert len(data["data"]["items"]) == 1
        assert data["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_list_documents_with_status_filter(self, client, sample_document_data):
        """GET /knowledge/documents?status=published 过滤。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        # 导入的文档是 review_pending，过滤 published 应为空
        resp = await client.get("/knowledge/documents", params={"status": "published"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 0
        assert data["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_unified_response_format(self, client, sample_document_data):
        """所有端点返回统一响应格式。"""
        resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        data = resp.json()
        assert "request_id" in data
        assert "data" in data
        assert "error" in data


class TestDocumentTransition:
    """知识状态转移端点测试。"""

    @pytest.fixture
    async def client(self):
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_transition_to_published_200(self, client, sample_document_data):
        """POST /knowledge/documents/{id}/transition {next_state: published} 应返回 200。"""
        import_resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        job_id = import_resp.json()["data"]["job_id"]

        # 先获取文档 ID
        list_resp = await client.get("/knowledge/documents")
        doc_id = list_resp.json()["data"]["items"][0]["document_id"]

        resp = await client.post(
            f"/knowledge/documents/{doc_id}/transition",
            json={"next_state": "published"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "published"

    @pytest.mark.asyncio
    async def test_transition_illegal_409(self, client, sample_document_data):
        """非法转移应返回 409。"""
        import_resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        list_resp = await client.get("/knowledge/documents")
        doc_id = list_resp.json()["data"]["items"][0]["document_id"]

        # published → review_pending 非法
        resp = await client.post(
            f"/knowledge/documents/{doc_id}/transition",
            json={"next_state": "expired"},
        )
        assert resp.status_code == 409
        error = resp.json()["error"]
        assert error["code"] == "ILLEGAL_TRANSITION"

    @pytest.mark.asyncio
    async def test_transition_document_not_found_404(self, client):
        """不存在的文档应返回 404。"""
        resp = await client.post(
            "/knowledge/documents/NONEXIST/transition",
            json={"next_state": "published"},
        )
        assert resp.status_code == 404
        error = resp.json()["error"]
        assert error["code"] == "DOCUMENT_NOT_FOUND"


class TestSearchEndpoint:
    """知识检索端点测试。"""

    @pytest.fixture
    async def client(self):
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_search_empty_query_400(self, client):
        """空搜索词应返回 400。"""
        resp = await client.get("/knowledge/search", params={"q": ""})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_unpublished_not_found(self, client, sample_document_data):
        """未发布文档不应被检索到。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        resp = await client.get("/knowledge/search", params={"q": "测试正文"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["results"]) == 0

    @pytest.mark.asyncio
    async def test_search_published_found(self, client, sample_document_data):
        """已发布文档应被检索到。"""
        import_resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        list_resp = await client.get("/knowledge/documents")
        doc_id = list_resp.json()["data"]["items"][0]["document_id"]

        await client.post(
            f"/knowledge/documents/{doc_id}/transition",
            json={"next_state": "published"},
        )

        resp = await client.get("/knowledge/search", params={"q": "测试正文"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["results"]) > 0
        assert data["data"]["results"][0]["score"] > 0


class TestAdminEndpoints:
    """管理员端点测试。"""

    @pytest.fixture
    async def client(self):
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_import_jobs_200(self, client, sample_document_data):
        """GET /knowledge/import-jobs 应返回任务列表。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        resp = await client.get("/knowledge/import-jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["total"] == 1
        assert data["data"]["items"][0]["status"] == "review_pending"

    @pytest.mark.asyncio
    async def test_import_jobs_with_status_filter(self, client, sample_document_data):
        """GET /knowledge/import-jobs?status= 过滤。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        resp = await client.get("/knowledge/import-jobs", params={"status": "failed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_reset_runtime_200(self, client):
        """POST /knowledge/runtime/reset 应返回 200 和 3 份样例。"""
        resp = await client.post("/knowledge/runtime/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "reset"
        assert data["data"]["sample_count"] == 3

    @pytest.mark.asyncio
    async def test_reset_removes_imported_docs(self, client, sample_document_data):
        """reset 应清除所有导入的文档，保留预置样例。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        # 验证导入后
        list_before = await client.get("/knowledge/documents")
        assert list_before.json()["data"]["total"] == 1

        # reset
        await client.post("/knowledge/runtime/reset")

        # 验证 reset 后
        list_after = await client.get("/knowledge/documents")
        assert list_after.json()["data"]["total"] == 3

    @pytest.mark.asyncio
    async def test_audit_200(self, client, sample_document_data):
        """GET /knowledge/audit 应返回审计事件列表。"""
        await client.post("/knowledge/documents/import", json=sample_document_data)

        resp = await client.get("/knowledge/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert len(data["data"]["items"]) >= 1

    @pytest.mark.asyncio
    async def test_audit_with_document_id_filter(self, client, sample_document_data):
        """GET /knowledge/audit?document_id= 过滤。"""
        import_resp = await client.post("/knowledge/documents/import", json=sample_document_data)
        list_resp = await client.get("/knowledge/documents")
        doc_id = list_resp.json()["data"]["items"][0]["document_id"]

        resp = await client.get("/knowledge/audit", params={"document_id": doc_id})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) >= 1

    @pytest.mark.asyncio
    async def test_preset_samples_searchable(self, client):
        """reset 后预置样例应可被检索。"""
        await client.post("/knowledge/runtime/reset")

        resp = await client.get("/knowledge/search", params={"q": "青霉素"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["results"]) > 0


class TestAuditLogs:
    """知识操作审计日志补全测试（Phase 1a：检索 / 删除）。"""

    @pytest.fixture
    async def client(self):
        from zhenhu.knowledge.main import app
        from zhenhu.knowledge.models import async_engine, Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_search_produces_audit_log(self, client):
        """检索操作应产生 knowledge_search 审计记录。"""
        from sqlalchemy import select
        from zhenhu.knowledge.models import KnowledgeAuditLog, async_session_factory

        # 先 reset 出可检索的预置样例
        await client.post("/knowledge/runtime/reset")

        resp = await client.get("/knowledge/search", params={"q": "青霉素"})
        assert resp.status_code == 200

        async with async_session_factory() as session:
            result = await session.execute(
                select(KnowledgeAuditLog).where(
                    KnowledgeAuditLog.action_type == "knowledge_search"
                )
            )
            logs = list(result.scalars().all())

        assert len(logs) >= 1
        search_log = logs[-1]
        assert search_log.actor == "system"
        assert search_log.session_id is not None

    @pytest.mark.asyncio
    async def test_reset_produces_deletion_audit(self, client, sample_document_data):
        """运行时重置删除应产生 knowledge_deleted 审计记录。"""
        from sqlalchemy import select
        from zhenhu.knowledge.models import KnowledgeAuditLog, async_session_factory

        # 导入一份文档后 reset，删除数量应 >= 1
        await client.post("/knowledge/documents/import", json=sample_document_data)
        await client.post("/knowledge/runtime/reset")

        async with async_session_factory() as session:
            result = await session.execute(
                select(KnowledgeAuditLog).where(
                    KnowledgeAuditLog.action_type == "knowledge_deleted"
                )
            )
            logs = list(result.scalars().all())

        assert len(logs) >= 1
        deleted_log = logs[-1]
        assert deleted_log.actor == "knowledge_admin"
        assert deleted_log.resource_type == "knowledge"
        assert deleted_log.detail is not None
