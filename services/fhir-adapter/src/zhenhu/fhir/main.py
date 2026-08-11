"""FastAPI 应用入口 —— fhir-adapter 服务。

提供 FHIR 资源适配 API，包括患者查询、照护计划、同意管理和访问审计。
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zhenhu.contracts.middleware import RequestIdMiddleware, setup_error_handlers
from zhenhu.fhir.routes import patients_router, fhir_ops_router, patient_care_router

VERSION = "0.2.0"

# 服务根目录（.../services/fhir-adapter）
_SERVICE_ROOT = Path(__file__).resolve().parents[3]


def _should_run_migrations() -> bool:
    """生产环境（APP_ENV=production 或 DATABASE_URL 为 mysql）执行 Alembic 迁移。

    测试/开发（SQLite）保持原 create_all 路径，确保现有测试不受影响。
    """
    env = os.environ.get("APP_ENV", "").lower()
    db_url = os.environ.get("DATABASE_URL", "").lower()
    return env == "production" or "mysql" in db_url


async def _run_migrations() -> None:
    """编程式执行 Alembic 迁移至最新版本（alembic upgrade head）。

    对既有 create_all 遗留库（无 alembic_version）做幂等引导：
    1. 检测 alembic_version 表是否存在；
    2. 无 alembic_version 且库内已有业务表（legacy 库）→ 先用
       Base.metadata.create_all(checkfirst=True) 幂等补表（补缺失新表，
       不重建已有表），再 alembic stamp head 标记基线；
    3. 之后正常 upgrade head（幂等）。
    全新空库仍走 upgrade head 由迁移脚本建表；已迁移库直接 upgrade head。

    env.py 内部使用 asyncio.run() 驱动异步引擎，因此必须在独立线程中执行，
    避免与当前运行中的事件循环冲突（FastAPI lifespan 运行在事件循环内）。
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect as sa_inspect

    from zhenhu.fhir.models import Base, async_engine

    async def _existing_tables() -> set[str]:
        async with async_engine.connect() as conn:
            def _get(sync_conn):
                return set(sa_inspect(sync_conn).get_table_names())
            return await conn.run_sync(_get)

    tables = await _existing_tables()
    # legacy 库：库内已有业务表但尚未纳入 Alembic 管理
    is_legacy = "alembic_version" not in tables and bool(tables)

    if is_legacy:
        # 幂等补表：补缺失表，不重建已有表
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    def _migrate() -> None:
        cfg = Config(str(_SERVICE_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_SERVICE_ROOT / "migrations"))
        if is_legacy:
            command.stamp(cfg, "head")
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_migrate)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：初始化数据库表结构并写入预置模拟患者数据。"""
    from zhenhu.fhir.models import (
        CarePlan,
        Condition,
        Encounter,
        MedicationRequest,
        Observation,
        Patient,
        init_db,
        async_session_factory,
    )

    if _should_run_migrations():
        await _run_migrations()
    else:
        # 测试/开发（SQLite）回退：仍走 create_all，不强制测试走 Alembic
        await init_db()

    # 写入预置模拟患者数据（幂等：检查是否已存在）
    async with async_session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Patient).where(Patient.patient_id == "pat-demo-001")
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            # 1. 患者
            demo_patient = Patient(
                patient_id="pat-demo-001",
                name="演示患者",
                gender="male",
                birth_date=date(1960, 1, 1),
                identifiers_json='["ID-19600101-1234"]',
            )
            session.add(demo_patient)
            await session.flush()

            # 2. 就诊记录（出院去向=home）
            demo_encounter = Encounter(
                encounter_id="enc-demo-001",
                patient_id="pat-demo-001",
                encounter_type="inpatient",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 10),
                discharge_to="home",
            )
            session.add(demo_encounter)

            # 3. 诊断：高血压 + 糖尿病
            session.add_all([
                Condition(
                    condition_id="cond-demo-001",
                    patient_id="pat-demo-001",
                    code="I10",
                    display="原发性高血压",
                    severity="moderate",
                    onset_date=date(2020, 1, 15),
                ),
                Condition(
                    condition_id="cond-demo-002",
                    patient_id="pat-demo-001",
                    code="E11",
                    display="2型糖尿病",
                    severity="mild",
                    onset_date=date(2019, 6, 1),
                ),
            ])

            # 4. 检验/体征：血压 + 血糖
            session.add_all([
                Observation(
                    observation_id="obs-demo-001",
                    patient_id="pat-demo-001",
                    code="8480-6",
                    display="收缩压",
                    value="135",
                    unit="mmHg",
                    effective_date=date(2025, 1, 10),
                ),
                Observation(
                    observation_id="obs-demo-002",
                    patient_id="pat-demo-001",
                    code="14749-6",
                    display="空腹血糖",
                    value="6.2",
                    unit="mmol/L",
                    effective_date=date(2025, 1, 10),
                ),
            ])

            # 5. 用药医嘱：氨氯地平 + 二甲双胍
            session.add_all([
                MedicationRequest(
                    med_request_id="med-demo-001",
                    patient_id="pat-demo-001",
                    medication_code="amlodipine",
                    medication_display="氨氯地平片 5mg",
                    dosage="每日一次 5mg",
                    status="active",
                ),
                MedicationRequest(
                    med_request_id="med-demo-002",
                    patient_id="pat-demo-001",
                    medication_code="metformin",
                    medication_display="二甲双胍片 500mg",
                    dosage="每日两次 500mg",
                    status="active",
                ),
            ])

            # 6. 照护计划：出院计划（discharge）+ 慢病计划（chronic）+ 出院后高血压管理
            session.add_all([
                CarePlan(
                    care_plan_id="cp-demo-001",
                    patient_id="pat-demo-001",
                    title="出院随访计划",
                    intent="plan",
                    category="discharge",
                    status="active",
                    period_start=date(2025, 1, 10),
                    period_end=date(2025, 2, 10),
                ),
                CarePlan(
                    care_plan_id="cp-demo-002",
                    patient_id="pat-demo-001",
                    title="慢病随访计划",
                    intent="order",
                    category="chronic",
                    status="active",
                    period_start=date(2025, 1, 10),
                    period_end=date(2025, 7, 10),
                ),
                CarePlan(
                    care_plan_id="cp-demo-003",
                    patient_id="pat-demo-001",
                    title="出院后高血压管理计划",
                    intent="plan",
                    category="discharge",
                    status="active",
                    period_start=date(2026, 7, 16),
                    period_end=None,
                ),
            ])

            await session.commit()

    yield


app = FastAPI(
    title="臻护 FHIR Adapter",
    description="FHIR 适配服务：患者资源管理、脱敏输出与访问审计",
    version=VERSION,
    lifespan=lifespan,
)

# CORS 配置 —— 阶段 0 允许本地前端开发跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求 ID 中间件（透传/注入 X-Request-ID）
app.add_middleware(RequestIdMiddleware)

# 统一错误处理
setup_error_handlers(app)

# 注册路由
app.include_router(patients_router)
app.include_router(fhir_ops_router)
app.include_router(patient_care_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """健康检查端点。

    Returns:
        {"status": "ok", "version": "0.2.0", "timestamp": "..."}
    """
    return {
        "status": "ok",
        "service": "fhir-adapter",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
