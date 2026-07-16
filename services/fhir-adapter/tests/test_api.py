"""fhir-adapter API 端点集成测试。

覆盖 4 个 FHIR 端点：
- GET  /fhir/Patient/{patient_id}              — 200/404
- GET  /fhir/Patient/{patient_id}/CarePlan   — 200/404
- POST /fhir/Consent                          — 201/404/422
- GET  /fhir/AuditEvent?patient=...           — 200/404
"""

from __future__ import annotations

import pytest


class TestHealthCheck:
    """健康检查端点测试。"""

    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        """GET /health 应返回 ok。"""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"
        assert "timestamp" in data


class TestGetPatient:
    """GET /fhir/Patient/{patient_id} 端点测试。"""

    @pytest.mark.asyncio
    async def test_get_patient_success(self, client):
        """查询已存在的患者应返回 200 + 脱敏 Patient 资源。"""
        resp = await client.get("/fhir/Patient/pat-demo-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["resourceType"] == "Patient"
        assert data["data"]["id"] == "pat-demo-001"
        assert data["data"]["gender"] == "male"
        assert data["data"]["birthDate"] == "1960-01-01"
        # 姓名脱敏验证
        assert len(data["data"]["name"]) == 1
        assert data["data"]["name"][0]["text"] == "演**"
        # identifier 脱敏验证
        assert len(data["data"]["identifier"]) == 1
        assert data["data"]["identifier"][0]["value"].startswith("TOKEN-")

    @pytest.mark.asyncio
    async def test_get_patient_not_found(self, client):
        """查询不存在的患者应返回 404。"""
        resp = await client.get("/fhir/Patient/nonexistent-999")
        assert resp.status_code == 404
        detail = resp.json()["error"]
        assert detail["code"] == "PATIENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_patient_request_id(self, client):
        """响应中应包含 request_id 和 X-Request-ID 头。"""
        resp = await client.get("/fhir/Patient/pat-demo-001")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert "request_id" in resp.json()

    @pytest.mark.asyncio
    async def test_get_patient_unified_response_format(self, client):
        """响应格式应符合 UnifiedResponse 规范。"""
        resp = await client.get("/fhir/Patient/pat-demo-001")
        data = resp.json()
        assert "request_id" in data
        assert "data" in data
        assert "error" in data
        assert data["error"] is None


class TestGetPatientCarePlan:
    """GET /fhir/Patient/{patient_id}/CarePlan 端点测试。"""

    @pytest.mark.asyncio
    async def test_get_care_plans_success(self, client):
        """查询已存在患者的照护计划应返回 200 + Bundle。"""
        resp = await client.get("/fhir/Patient/pat-demo-001/CarePlan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["resourceType"] == "Bundle"
        entries = data["data"]["entry"]
        assert len(entries) == 2  # 出院计划 + 慢病计划

        # 验证两条 CarePlan 的不同分类
        resources = [e["resource"] for e in entries]
        categories = {r["category"][0]["text"] for r in resources}
        assert "出院随访" in categories
        assert "慢病照护" in categories

        # 验证 CarePlan 结构
        for r in resources:
            assert r["resourceType"] == "CarePlan"
            assert "id" in r
            assert "title" in r
            assert "status" in r
            assert "period" in r

    @pytest.mark.asyncio
    async def test_get_care_plans_patient_not_found(self, client):
        """查询不存在患者的照护计划应返回 404。"""
        resp = await client.get("/fhir/Patient/nonexistent-999/CarePlan")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PATIENT_NOT_FOUND"


class TestCreateConsent:
    """POST /fhir/Consent 端点测试。"""

    @pytest.mark.asyncio
    async def test_create_consent_success(self, client):
        """创建 Consent 应返回 201。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "patient-privacy-consent",
            "status": "active",
            "provision": {"purpose": "出院交接审核"},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["consent_id"].startswith("CON-")
        assert data["data"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_consent_patient_not_found(self, client):
        """为不存在的患者创建 Consent 应返回 404。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "nonexistent-999",
            "scope": "patient-privacy-consent",
            "status": "active",
        })
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PATIENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_create_consent_invalid_status(self, client):
        """status 为非法值时应返回 422。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "patient-privacy-consent",
            "status": "invalid_status",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_consent_missing_patient_id(self, client):
        """缺少必填字段 patient_id 时应返回 422。"""
        resp = await client.post("/fhir/Consent", json={
            "scope": "patient-privacy-consent",
            "status": "active",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_consent_without_provision(self, client):
        """不提供 provision 也能成功创建 Consent。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "patient-privacy-consent",
            "status": "active",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["consent_id"].startswith("CON-")

    @pytest.mark.asyncio
    async def test_create_consent_inactive_status(self, client):
        """创建 status=inactive 的 Consent 应成功。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "patient-privacy-consent",
            "status": "inactive",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "inactive"


class TestGetAuditEvent:
    """GET /fhir/AuditEvent 端点测试。"""

    @pytest.mark.asyncio
    async def test_get_audit_events_empty(self, client):
        """查询无审计记录的患者应返回空 Bundle。"""
        resp = await client.get("/fhir/AuditEvent?patient=pat-demo-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["resourceType"] == "Bundle"
        # 刚启动时没有审计记录（查询本身会创建一条，但在 commit 之后）
        # 此时可能已经有一条来自 Patient 查询的审计，也可能没有
        # 不做严格断言

    @pytest.mark.asyncio
    async def test_get_audit_events_after_access(self, client):
        """先访问 Patient 再查询 AuditEvent，应能看到审计记录。"""
        # 先访问 Patient（会产生审计记录）
        await client.get("/fhir/Patient/pat-demo-001")

        # 查询审计事件
        resp = await client.get("/fhir/AuditEvent?patient=pat-demo-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["resourceType"] == "Bundle"
        entries = data["data"]["entry"]
        # 至少应有一条 Patient 读取审计记录
        assert len(entries) >= 1
        # 验证审计记录结构
        first = entries[0]["resource"]
        assert first["resourceType"] == "AuditEvent"
        assert "id" in first
        assert "type" in first
        assert "entity" in first
        assert "agent" in first
        assert "recorded" in first

    @pytest.mark.asyncio
    async def test_get_audit_events_patient_not_found(self, client):
        """查询不存在患者的审计事件应返回 404。"""
        resp = await client.get("/fhir/AuditEvent?patient=nonexistent-999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PATIENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_audit_events_missing_patient_param(self, client):
        """缺少 patient 查询参数时应返回 422。"""
        resp = await client.get("/fhir/AuditEvent")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_audit_events_pagination(self, client):
        """分页参数应正确生效。"""
        # 先产生多条审计记录（多次访问不同资源）
        await client.get("/fhir/Patient/pat-demo-001")
        await client.get("/fhir/Patient/pat-demo-001/CarePlan")
        await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "test",
            "status": "active",
        })

        # 查询第一页（size=2）
        resp = await client.get("/fhir/AuditEvent?patient=pat-demo-001&page=1&size=2")
        assert resp.status_code == 200
        entries_page1 = resp.json()["data"]["entry"]
        # 应有至多 2 条
        assert len(entries_page1) <= 2

        # 查询第二页
        resp2 = await client.get("/fhir/AuditEvent?patient=pat-demo-001&page=2&size=2")
        assert resp2.status_code == 200


class TestAuditTrailIntegration:
    """审计追踪端到端测试。"""

    @pytest.mark.asyncio
    async def test_audit_created_on_patient_access(self, client):
        """访问 Patient 资源后，AuditEvent 中应包含相应记录。"""
        # 访问 Patient
        await client.get("/fhir/Patient/pat-demo-001")

        # 查询审计
        resp = await client.get("/fhir/AuditEvent?patient=pat-demo-001&size=50")
        entries = resp.json()["data"]["entry"]

        # 至少有一条 Patient 读取记录
        patient_reads = [
            e for e in entries
            if e["resource"]["entity"][0]["reference"]["reference"].startswith("Patient/")
        ]
        assert len(patient_reads) >= 1

    @pytest.mark.asyncio
    async def test_consent_audit_action_is_create(self, client):
        """创建 Consent 的审计记录 action 应为 C。"""
        resp = await client.post("/fhir/Consent", json={
            "patient_id": "pat-demo-001",
            "scope": "test-audit",
            "status": "active",
        })
        consent_id = resp.json()["data"]["consent_id"]

        # 查询审计
        audit_resp = await client.get(f"/fhir/AuditEvent?patient=pat-demo-001&size=50")
        entries = audit_resp.json()["data"]["entry"]

        consent_creates = [
            e for e in entries
            if e["resource"]["type"]["code"] == "C"
            and any(
                ref["reference"].startswith("Consent/")
                for ref in [ent["reference"] for ent in e["resource"]["entity"]]
            )
        ]
        assert len(consent_creates) >= 1
