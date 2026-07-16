"""SQLAlchemy ORM 模型 —— fhir-adapter 数据层。

对照需求 §6.1 FHIR 映射表，定义 8 张核心资源表：
Patient、Encounter、Condition、Observation、MedicationRequest、
CarePlan、Consent、FHIRAuditEvent。

阶段 0 使用 SQLite :memory: 进行测试。
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from zhenhu.contracts import get_session as _contracts_get_session  # 阶段J审计修复

# 测试用临时文件数据库；生产环境通过 DATABASE_URL 环境变量覆盖
_test_db = os.path.join(tempfile.gettempdir(), "zhenhu_fhir_test.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db}")

async_engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


def _utcnow() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def _new_id(prefix: str = "") -> str:
    """生成带前缀的唯一标识符。

    Args:
        prefix: ID 前缀（如 "PAT-", "ENC-" 等）。

    Returns:
        带前缀的 12 位十六进制随机标识符。
    """
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ============================================================================
# 8 张 FHIR 资源表
# ============================================================================


class Patient(Base):
    """患者实体 —— FHIR Patient 资源映射。

    对照需求 §6.1：患者与主索引 → Patient。
    """

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("PAT-"),
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="患者姓名（脱敏输出时替换为 token）")
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="性别：male/female/other")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    identifiers_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="证件标识 JSON 数组（脱敏后为 token）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, comment="记录创建时间"
    )

    # 反向关联：一个患者可拥有多条就诊、诊断、检验、用药、照护计划、同意、审计记录
    encounters: Mapped[list["Encounter"]] = relationship(
        "Encounter", back_populates="patient", cascade="all, delete-orphan"
    )
    conditions: Mapped[list["Condition"]] = relationship(
        "Condition", back_populates="patient", cascade="all, delete-orphan"
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation", back_populates="patient", cascade="all, delete-orphan"
    )
    medication_requests: Mapped[list["MedicationRequest"]] = relationship(
        "MedicationRequest", back_populates="patient", cascade="all, delete-orphan"
    )
    care_plans: Mapped[list["CarePlan"]] = relationship(
        "CarePlan", back_populates="patient", cascade="all, delete-orphan"
    )
    consents: Mapped[list["Consent"]] = relationship(
        "Consent", back_populates="patient", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["FHIRAuditEvent"]] = relationship(
        "FHIRAuditEvent", back_populates="patient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Patient(patient_id={self.patient_id!r}, name={self.name!r})>"


class Encounter(Base):
    """就诊记录实体 —— FHIR Encounter 资源映射。

    对照需求 §6.1：就诊与出院 → Encounter。
    """

    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("ENC-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    encounter_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="就诊类型：inpatient/outpatient/emergency"
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="就诊开始日期")
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="就诊结束/出院日期")
    discharge_to: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="出院去向：home/rehabilitation/other"
    )

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="encounters")

    def __repr__(self) -> str:
        return f"<Encounter(encounter_id={self.encounter_id!r}, type={self.encounter_type!r})>"


class Condition(Base):
    """诊断/病情实体 —— FHIR Condition 资源映射。

    对照需求 §6.1：诊断与慢病 → Condition。
    """

    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    condition_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("COND-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="诊断编码（如 ICD-10：I10）"
    )
    display: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment='诊断显示名（如"原发性高血压"）'
    )
    severity: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="严重程度：mild/moderate/severe"
    )
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="发病/确诊日期")

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="conditions")

    def __repr__(self) -> str:
        return f"<Condition(condition_id={self.condition_id!r}, display={self.display!r})>"


class Observation(Base):
    """检验/体征实体 —— FHIR Observation 资源映射。

    对照需求 §6.1：检验、生命体征、量表 → Observation。
    """

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("OBS-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="检验编码（如 LOINC：8480-6）"
    )
    display: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment='检验项显示名（如"收缩压"）'
    )
    value: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="检验数值（字符串形式）"
    )
    unit: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="单位（如 mmHg, mmol/L）"
    )
    effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检验/测量有效日期"
    )

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="observations")

    def __repr__(self) -> str:
        return f"<Observation(observation_id={self.observation_id!r}, display={self.display!r})>"


class MedicationRequest(Base):
    """用药医嘱实体 —— FHIR MedicationRequest 资源映射。

    对照需求 §6.1：药物与医嘱 → MedicationRequest。
    """

    __tablename__ = "medication_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    med_request_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("MED-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    medication_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="药品编码（如 ATC/院内编码）"
    )
    medication_display: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment='药品显示名（如"氨氯地平片 5mg"）'
    )
    dosage: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment='用法用量（如"每日一次 5mg"）'
    )
    status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="医嘱状态：active/completed/stopped"
    )

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="medication_requests")

    def __repr__(self) -> str:
        return f"<MedicationRequest(med_request_id={self.med_request_id!r}, display={self.medication_display!r})>"


class CarePlan(Base):
    """照护计划实体 —— FHIR CarePlan 资源映射。

    对照需求 §6.1：随访与照护计划 → CarePlan。
    CarePlan 双模式：出院交接计划（intent=plan, 短期）和慢病照护计划（intent=order, 长期）。
    """

    __tablename__ = "care_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    care_plan_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("CP-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    title: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="照护计划标题"
    )
    intent: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="意图：plan（出院计划）/ order（慢病照护）"
    )
    category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="分类：discharge（出院）/ chronic（慢病）"
    )
    status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="状态：active/completed/revoked"
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, comment="计划起始日期")
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, comment="计划结束日期")

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="care_plans")

    def __repr__(self) -> str:
        return f"<CarePlan(care_plan_id={self.care_plan_id!r}, category={self.category!r})>"


class Consent(Base):
    """知情同意实体 —— FHIR Consent 资源映射。

    对照需求 §6.1：授权、数据来源与审计 → Consent。
    """

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consent_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("CON-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    scope: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="授权范围（如 patient-privacy-consent）"
    )
    status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="同意状态：active/inactive"
    )
    granted_to: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="授权对象（角色/组织/用途）"
    )

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="consents")

    def __repr__(self) -> str:
        return f"<Consent(consent_id={self.consent_id!r}, status={self.status!r})>"


class FHIRAuditEvent(Base):
    """FHIR 访问审计实体 —— FHIR AuditEvent 资源映射。

    对照需求 §6.1：授权、数据来源与审计 → AuditEvent。
    每次 FHIR 资源访问均写入此表，审计记录不可修改（INSERT-only）。
    """

    __tablename__ = "fhir_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True,
        default=lambda: _new_id("AUDIT-"),
    )
    patient_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("patients.patient_id"), nullable=False, index=True,
        comment="所属患者 ID",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="被访问的 FHIR 资源类型：Patient/Observation/CarePlan/…"
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="被访问的资源 ID"
    )
    action: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="操作类型：C（创建）/ R（读取）/ U（更新）/ D（删除）"
    )
    actor: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="操作人角色（如 doctor/nurse）"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, comment="操作发生时间"
    )

    # 反向关联
    patient: Mapped["Patient"] = relationship("Patient", back_populates="audit_events")

    def __repr__(self) -> str:
        return f"<FHIRAuditEvent(audit_id={self.audit_id!r}, action={self.action!r})>"


# ============================================================================
# 数据库初始化与会话管理
# ============================================================================


async def init_db() -> None:
    """初始化数据库表结构（创建所有表）。"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # 阶段J审计修复: 委托 contracts 统一实现
    """获取一个新的异步数据库会话（用于 FastAPI 依赖注入） —— 阶段J审计修复。

    Yields:
        AsyncSession: SQLAlchemy 异步会话实例。
    """
    async for session in _contracts_get_session(async_session_factory):
        yield session
