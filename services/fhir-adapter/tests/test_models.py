"""fhir-adapter ORM 模型层测试。

覆盖 8 张表的 CRUD 操作、FK 约束、级联删除和默认值行为。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from zhenhu.fhir.models import (
    CarePlan,
    Condition,
    Consent,
    Encounter,
    FHIRAuditEvent,
    MedicationRequest,
    Observation,
    Patient,
)


class TestPatientCRUD:
    """Patient 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_patient(self, db_session):
        """创建患者记录应成功，自动生成 patient_id。"""
        patient = Patient(name="测试患者", gender="male", birth_date=date(1970, 5, 15))
        db_session.add(patient)
        await db_session.flush()

        assert patient.id is not None
        assert patient.patient_id.startswith("PAT-")
        assert patient.name == "测试患者"
        assert patient.gender == "male"
        assert patient.created_at is not None

    @pytest.mark.asyncio
    async def test_query_patient_by_id(self, db_session):
        """通过 patient_id 查询患者应返回正确记录。"""
        patient = Patient(patient_id="pat-test-001", name="查询测试", gender="female")
        db_session.add(patient)
        await db_session.flush()

        result = await db_session.execute(
            select(Patient).where(Patient.patient_id == "pat-test-001")
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.name == "查询测试"
        assert found.gender == "female"

    @pytest.mark.asyncio
    async def test_update_patient_name(self, db_session):
        """更新患者姓名应成功持久化。"""
        patient = Patient(patient_id="pat-update-001", name="原始姓名")
        db_session.add(patient)
        await db_session.flush()

        patient.name = "更新后姓名"
        await db_session.flush()

        result = await db_session.execute(
            select(Patient).where(Patient.patient_id == "pat-update-001")
        )
        found = result.scalar_one_or_none()
        assert found.name == "更新后姓名"

    @pytest.mark.asyncio
    async def test_delete_patient(self, db_session):
        """删除患者记录应成功。"""
        patient = Patient(patient_id="pat-del-001", name="待删除")
        db_session.add(patient)
        await db_session.flush()

        await db_session.delete(patient)
        await db_session.flush()

        result = await db_session.execute(
            select(Patient).where(Patient.patient_id == "pat-del-001")
        )
        assert result.scalar_one_or_none() is None


class TestEncounterCRUD:
    """Encounter 表 CRUD 与 FK 约束测试。"""

    @pytest.mark.asyncio
    async def test_create_encounter_with_patient(self, db_session):
        """创建关联患者的就诊记录应成功。"""
        patient = Patient(patient_id="pat-enc-001", name="就诊患者")
        db_session.add(patient)
        await db_session.flush()

        encounter = Encounter(
            encounter_id="enc-test-001",
            patient_id="pat-enc-001",
            encounter_type="inpatient",
            discharge_to="home",
        )
        db_session.add(encounter)
        await db_session.flush()

        assert encounter.encounter_id == "enc-test-001"
        assert encounter.patient_id == "pat-enc-001"

    @pytest.mark.asyncio
    async def test_encounter_fk_constraint(self, db_session):
        """不存在的 patient_id 应触发 FK 约束错误。"""
        encounter = Encounter(
            encounter_id="enc-orphan-001",
            patient_id="nonexistent-patient",
            encounter_type="outpatient",
        )
        db_session.add(encounter)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cascade_delete_encounters(self, db_session):
        """删除患者时应级联删除其就诊记录。"""
        patient = Patient(patient_id="pat-cascade-001", name="级联测试")
        db_session.add(patient)
        await db_session.flush()

        encounter = Encounter(patient_id="pat-cascade-001", encounter_type="inpatient")
        db_session.add(encounter)
        await db_session.flush()

        await db_session.delete(patient)
        await db_session.flush()

        result = await db_session.execute(
            select(Encounter).where(Encounter.patient_id == "pat-cascade-001")
        )
        assert result.scalar_one_or_none() is None


class TestConditionCRUD:
    """Condition 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_conditions(self, db_session):
        """创建多条诊断记录应成功。"""
        patient = Patient(patient_id="pat-cond-001", name="诊断患者")
        db_session.add(patient)
        await db_session.flush()

        c1 = Condition(patient_id="pat-cond-001", code="I10", display="原发性高血压", severity="moderate")
        c2 = Condition(patient_id="pat-cond-001", code="E11", display="2型糖尿病", severity="mild")
        db_session.add_all([c1, c2])
        await db_session.flush()

        result = await db_session.execute(
            select(Condition).where(Condition.patient_id == "pat-cond-001")
        )
        conditions = result.scalars().all()
        assert len(conditions) == 2

    @pytest.mark.asyncio
    async def test_condition_default_id(self, db_session):
        """未指定 condition_id 时应自动生成。"""
        patient = Patient(patient_id="pat-auto-cond", name="自动ID")
        db_session.add(patient)
        await db_session.flush()

        cond = Condition(patient_id="pat-auto-cond", display="测试诊断")
        db_session.add(cond)
        await db_session.flush()

        assert cond.condition_id.startswith("COND-")


class TestObservationCRUD:
    """Observation 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_observation(self, db_session):
        """创建检验记录应成功。"""
        patient = Patient(patient_id="pat-obs-001", name="检验患者")
        db_session.add(patient)
        await db_session.flush()

        obs = Observation(
            patient_id="pat-obs-001",
            code="8480-6",
            display="收缩压",
            value="120",
            unit="mmHg",
            effective_date=date(2025, 1, 15),
        )
        db_session.add(obs)
        await db_session.flush()

        assert obs.value == "120"
        assert obs.unit == "mmHg"


class TestMedicationRequestCRUD:
    """MedicationRequest 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_medication(self, db_session):
        """创建用药医嘱应成功。"""
        patient = Patient(patient_id="pat-med-001", name="用药患者")
        db_session.add(patient)
        await db_session.flush()

        med = MedicationRequest(
            patient_id="pat-med-001",
            medication_code="amlodipine",
            medication_display="氨氯地平片 5mg",
            dosage="每日一次 5mg",
            status="active",
        )
        db_session.add(med)
        await db_session.flush()

        assert med.medication_code == "amlodipine"
        assert med.status == "active"


class TestCarePlanCRUD:
    """CarePlan 表 CRUD 与双模式测试。"""

    @pytest.mark.asyncio
    async def test_create_care_plan_dual_mode(self, db_session):
        """创建出院计划+慢病计划两条 CarePlan 应成功。"""
        patient = Patient(patient_id="pat-cp-001", name="照护患者")
        db_session.add(patient)
        await db_session.flush()

        discharge_cp = CarePlan(
            patient_id="pat-cp-001",
            intent="plan",
            category="discharge",
            status="active",
            period_start=date(2025, 1, 10),
            period_end=date(2025, 2, 10),
        )
        chronic_cp = CarePlan(
            patient_id="pat-cp-001",
            intent="order",
            category="chronic",
            status="active",
            period_start=date(2025, 1, 10),
            period_end=date(2025, 7, 10),
        )
        db_session.add_all([discharge_cp, chronic_cp])
        await db_session.flush()

        result = await db_session.execute(
            select(CarePlan).where(CarePlan.patient_id == "pat-cp-001")
        )
        plans = result.scalars().all()
        assert len(plans) == 2
        categories = {p.category for p in plans}
        assert categories == {"discharge", "chronic"}


class TestConsentCRUD:
    """Consent 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_consent(self, db_session):
        """创建知情同意记录应成功。"""
        patient = Patient(patient_id="pat-con-001", name="同意患者")
        db_session.add(patient)
        await db_session.flush()

        consent = Consent(
            patient_id="pat-con-001",
            scope="patient-privacy-consent",
            status="active",
            granted_to="purpose=出院交接审核",
        )
        db_session.add(consent)
        await db_session.flush()

        assert consent.consent_id.startswith("CON-")
        assert consent.status == "active"


class TestFHIRAuditEventCRUD:
    """FHIRAuditEvent 表 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_audit_event(self, db_session):
        """创建审计事件应成功。"""
        patient = Patient(patient_id="pat-audit-001", name="审计患者")
        db_session.add(patient)
        await db_session.flush()

        audit = FHIRAuditEvent(
            patient_id="pat-audit-001",
            entity_type="Patient",
            entity_id="pat-audit-001",
            action="R",
            actor="doctor",
        )
        db_session.add(audit)
        await db_session.flush()

        assert audit.audit_id.startswith("AUDIT-")
        assert audit.action == "R"
        assert audit.actor == "doctor"
        assert audit.occurred_at is not None

    @pytest.mark.asyncio
    async def test_audit_event_occurred_at_auto_set(self, db_session):
        """审计事件 occurred_at 应自动设为当前时间。"""
        patient = Patient(patient_id="pat-auto-time", name="时间测试")
        db_session.add(patient)
        await db_session.flush()

        audit = FHIRAuditEvent(
            patient_id="pat-auto-time",
            entity_type="Observation",
            entity_id="obs-001",
            action="C",
            actor="nurse",
        )
        db_session.add(audit)
        await db_session.flush()

        assert audit.occurred_at is not None


class TestRelationshipNavigation:
    """ORM 关系导航测试。"""

    @pytest.mark.asyncio
    async def test_patient_encounters_navigation(self, db_session):
        """从 Patient 导航到 Encounter 应正确。"""
        patient = Patient(patient_id="pat-nav-001", name="导航患者")
        db_session.add(patient)
        await db_session.flush()

        e1 = Encounter(patient_id="pat-nav-001", encounter_type="inpatient")
        e2 = Encounter(patient_id="pat-nav-001", encounter_type="outpatient")
        db_session.add_all([e1, e2])
        await db_session.flush()

        # 重新查询以加载关系（使用 selectinload 预加载关联）
        result = await db_session.execute(
            select(Patient)
            .where(Patient.patient_id == "pat-nav-001")
            .options(selectinload(Patient.encounters))
        )
        loaded = result.scalar_one()
        assert len(loaded.encounters) == 2

    @pytest.mark.asyncio
    async def test_patient_all_relationships(self, db_session):
        """患者应能导航到所有关联资源。"""
        patient = Patient(patient_id="pat-all-rel", name="全关联")
        db_session.add(patient)
        await db_session.flush()

        db_session.add(Encounter(patient_id="pat-all-rel"))
        db_session.add(Condition(patient_id="pat-all-rel"))
        db_session.add(Observation(patient_id="pat-all-rel"))
        db_session.add(MedicationRequest(patient_id="pat-all-rel"))
        db_session.add(CarePlan(patient_id="pat-all-rel"))
        db_session.add(Consent(patient_id="pat-all-rel"))
        db_session.add(FHIRAuditEvent(patient_id="pat-all-rel", entity_type="Patient", entity_id="pat-all-rel", action="R"))
        await db_session.flush()

        # 使用 selectinload 预加载所有关联
        result = await db_session.execute(
            select(Patient)
            .where(Patient.patient_id == "pat-all-rel")
            .options(
                selectinload(Patient.encounters),
                selectinload(Patient.conditions),
                selectinload(Patient.observations),
                selectinload(Patient.medication_requests),
                selectinload(Patient.care_plans),
                selectinload(Patient.consents),
                selectinload(Patient.audit_events),
            )
        )
        loaded = result.scalar_one()
        assert len(loaded.encounters) == 1
        assert len(loaded.conditions) == 1
        assert len(loaded.observations) == 1
        assert len(loaded.medication_requests) == 1
        assert len(loaded.care_plans) == 1
        assert len(loaded.consents) == 1
        assert len(loaded.audit_events) == 1
