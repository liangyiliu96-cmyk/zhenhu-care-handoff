"""fhir-adapter 测试 fixtures。

提供 SQLite :memory: 数据库和 FastAPI AsyncClient。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """启用 SQLite 外键约束强制。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _create_test_engine(db_url: str = "sqlite+aiosqlite:///:memory:"):
    """创建测试引擎并注册 SQLite FK pragma。"""
    engine = create_async_engine(db_url, echo=False)
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    return engine


@pytest.fixture
async def client():
    """创建 AsyncClient 用于测试 FastAPI app（每次测试干净 :memory: 库）。

    数据库使用 SQLite :memory:，确保测试间隔离。
    """
    import os
    from zhenhu.fhir.main import app
    from zhenhu.fhir.models import Base
    import zhenhu.fhir.models as m

    # 强制使用 :memory: 数据库
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    m.async_engine = _create_test_engine()
    m.async_session_factory = async_sessionmaker(m.async_engine, class_=AsyncSession, expire_on_commit=False)

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all)

    # 写入预置模拟患者数据
    async with m.async_session_factory() as session:
        from datetime import date
        from zhenhu.fhir.models import (
            CarePlan, Condition, Encounter, MedicationRequest,
            Observation, Patient,
        )
        from sqlalchemy import select

        result = await session.execute(
            select(Patient).where(Patient.patient_id == "pat-demo-001")
        )
        if result.scalar_one_or_none() is None:
            demo_patient = Patient(
                patient_id="pat-demo-001",
                name="演示患者",
                gender="male",
                birth_date=date(1960, 1, 1),
                identifiers_json='["ID-19600101-1234"]',
            )
            session.add(demo_patient)
            await session.flush()

            session.add(Encounter(
                encounter_id="enc-demo-001",
                patient_id="pat-demo-001",
                encounter_type="inpatient",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 10),
                discharge_to="home",
            ))
            session.add_all([
                Condition(condition_id="cond-demo-001", patient_id="pat-demo-001",
                          code="I10", display="原发性高血压", severity="moderate",
                          onset_date=date(2020, 1, 15)),
                Condition(condition_id="cond-demo-002", patient_id="pat-demo-001",
                          code="E11", display="2型糖尿病", severity="mild",
                          onset_date=date(2019, 6, 1)),
            ])
            session.add_all([
                Observation(observation_id="obs-demo-001", patient_id="pat-demo-001",
                            code="8480-6", display="收缩压", value="135",
                            unit="mmHg", effective_date=date(2025, 1, 10)),
                Observation(observation_id="obs-demo-002", patient_id="pat-demo-001",
                            code="14749-6", display="空腹血糖", value="6.2",
                            unit="mmol/L", effective_date=date(2025, 1, 10)),
            ])
            session.add_all([
                MedicationRequest(med_request_id="med-demo-001", patient_id="pat-demo-001",
                                  medication_code="amlodipine", medication_display="氨氯地平片 5mg",
                                  dosage="每日一次 5mg", status="active"),
                MedicationRequest(med_request_id="med-demo-002", patient_id="pat-demo-001",
                                  medication_code="metformin", medication_display="二甲双胍片 500mg",
                                  dosage="每日两次 500mg", status="active"),
            ])
            session.add_all([
                CarePlan(care_plan_id="cp-demo-001", patient_id="pat-demo-001",
                         intent="plan", category="discharge", status="active",
                         period_start=date(2025, 1, 10), period_end=date(2025, 2, 10)),
                CarePlan(care_plan_id="cp-demo-002", patient_id="pat-demo-001",
                         intent="order", category="chronic", status="active",
                         period_start=date(2025, 1, 10), period_end=date(2025, 7, 10)),
            ])
            await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    """创建独立 :memory: 数据库会话（用于模型层单元测试）。"""
    import zhenhu.fhir.models as m

    m.async_engine = _create_test_engine()
    m.async_session_factory = async_sessionmaker(m.async_engine, class_=AsyncSession, expire_on_commit=False)

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all)
        # SQLite 默认不强制 FK，需要手动开启
        from sqlalchemy import text
        await conn.execute(text("PRAGMA foreign_keys = ON"))

    async with m.async_session_factory() as session:
        yield session

    async with m.async_engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)
