"""SQLAlchemy ORM 模型 —— 住院协同核心临床表(12表)。合并迁入。

自包含定义: 不依赖 app.db.tables.*, Base+TimestampMixin+全部表定义内联。
合并迁入修正: 移除对 simulated_actor/data_import_batch 的 FK 依赖,
 保留为普通 CHAR(36) 列, agent 代码不依赖 ORM, 后续阶段再补全关联。
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ============================================================================
# Base
# ============================================================================


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_short_name)s",
            "column_0_short_name": lambda constraint, table: getattr(constraint, "columns")
            .keys()[0]
            .removesuffix("_id"),
        }
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )


# ============================================================================
# ActorRole (内联, AuditLog 需要)
# ============================================================================


class ActorRole(enum.StrEnum):
    PATIENT = "patient"
    FAMILY = "family"
    CAREGIVER = "caregiver"
    DOCTOR = "doctor"
    COORDINATOR = "coordinator"
    SUPERVISOR = "supervisor"


class AuditActorRole(enum.StrEnum):
    PATIENT = ActorRole.PATIENT.value
    FAMILY = ActorRole.FAMILY.value
    CAREGIVER = ActorRole.CAREGIVER.value
    DOCTOR = ActorRole.DOCTOR.value
    COORDINATOR = ActorRole.COORDINATOR.value
    SUPERVISOR = ActorRole.SUPERVISOR.value
    SYSTEM = "system"


# ============================================================================
# 核心临床表(12表)
# ============================================================================


class Patient(Base, TimestampMixin):
    """患者基础档案表。"""

    __tablename__ = "inpatient_patients"
    __table_args__ = (
        UniqueConstraint("data_import_batch_id", "display_label", name="uq_patient_batch_label"),
        CheckConstraint("LENGTH(TRIM(display_label)) > 0", name="ck_patient_display_label_not_blank"),
        Index("ix_patient_data_batch", "data_import_batch_id"),
        {"comment": "患者基础档案表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="患者UUID主键")
    data_import_batch_id: Mapped[str] = mapped_column(
        CHAR(36), nullable=False, comment="来源批次(合并迁入: 移除FK,保留为普通列)"
    )
    display_label: Mapped[str] = mapped_column(String(100), nullable=False, comment="展示用患者标识")
    basic_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InpatientRecord(Base, TimestampMixin):
    """住院记录表。"""

    __tablename__ = "inpatient_records"
    __table_args__ = {"comment": "住院记录表"}

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="住院记录UUID主键")
    patient_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_patients.id", name="fk_inpatient_record_patient"),
        nullable=False, index=True,
    )
    current_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bed_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    admission_diagnosis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)


class MedicalHistory(Base, TimestampMixin):
    """病史记录表。"""

    __tablename__ = "medical_histories"
    __table_args__ = (
        UniqueConstraint("inpatient_record_id", name="uq_medical_history_inpatient_record"),
        UniqueConstraint("inpatient_record_id", "idempotency_key", name="uq_medical_history_record_idempotency"),
        {"comment": "病史记录表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="病史UUID主键")
    inpatient_record_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_records.id", name="fk_medical_history_inpatient_record"),
        nullable=False, index=True,
    )
    history_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(
        CHAR(36), nullable=True, comment="提交者(合并迁入: 移除 simulated_actor FK)"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirm_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Attachment(Base, TimestampMixin):
    """资料附件表。"""

    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("inpatient_record_id", "uploaded_by_actor_id", "content_hash", name="uq_attachment_patient_content_hash"),
        UniqueConstraint("inpatient_record_id", "uploaded_by_actor_id", "upload_idempotency_key", name="uq_attachment_patient_upload_idempotency"),
        {"comment": "资料附件表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="附件UUID主键")
    inpatient_record_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_records.id", name="fk_attachment_inpatient_record"),
        nullable=False, index=True,
    )
    medical_history_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("medical_histories.id", name="fk_attachment_medical_history"),
        nullable=True, index=True,
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_by_actor_id: Mapped[str] = mapped_column(
        CHAR(36), nullable=False, index=True, comment="上传者(合并迁入: 移除 simulated_actor FK)"
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    ocr_status: Mapped[str] = mapped_column(String(20), nullable=False)
    ocr_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_extraction_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BPEntry(Base, TimestampMixin):
    """生命体征记录表(原血压记录表) —— 通用化后支持多病种体征。"""

    __tablename__ = "vital_sign_entries"
    __table_args__ = (
        UniqueConstraint("handoff_context_id", "idempotency_key", name="uq_vital_sign_context_idempotency"),
        {"comment": "生命体征记录表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="体征记录UUID主键")
    handoff_context_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("handoff_contexts.id", name="fk_bp_entry_handoff_context"),
        nullable=False, index=True,
    )
    presentation_item_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("presentation_items.id", name="fk_bp_entry_presentation_item"),
        nullable=True, index=True,
    )
    input_actor_id: Mapped[str | None] = mapped_column(
        CHAR(36), nullable=True, comment="录入者(合并迁入: 移除 simulated_actor FK)"
    )
    related_feedback_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("item_feedbacks.id", name="fk_bp_entry_related_feedback"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    systolic_mmhg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic_mmhg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class HandoffContext(Base, TimestampMixin):
    """交接上下文表。"""

    __tablename__ = "handoff_contexts"
    __table_args__ = (
        UniqueConstraint("inpatient_record_id", name="uq_handoff_context_inpatient_record"),
        UniqueConstraint("discharge_instruction_id", name="uq_handoff_context_discharge_instruction"),
        {"comment": "交接上下文表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="交接上下文UUID主键")
    inpatient_record_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_records.id", name="fk_handoff_context_inpatient_record"),
        nullable=False, index=True,
    )
    discharge_instruction_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("discharge_instructions.id", name="fk_handoff_context_discharge_instruction"),
        nullable=False, index=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        CHAR(36), nullable=False, index=True, comment="医生(合并迁入: 移除 simulated_actor FK)"
    )
    handoff_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    handoff_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PresentationItem(Base, TimestampMixin):
    """交代事项表。"""

    __tablename__ = "presentation_items"
    __table_args__ = (
        UniqueConstraint("handoff_context_id", "projection_version", "item_type", name="uq_presentation_item_version_type"),
        {"comment": "交代事项表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="交代事项UUID主键")
    handoff_context_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("handoff_contexts.id", name="fk_presentation_item_handoff_context"),
        nullable=False, index=True,
    )
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    item_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_instruction_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ItemFeedback(Base, TimestampMixin):
    """逐项反馈表。"""

    __tablename__ = "item_feedbacks"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_item_feedback_actor_idempotency"),
        {"comment": "逐项反馈表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="反馈UUID主键")
    handoff_context_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("handoff_contexts.id", name="fk_item_feedback_handoff_context"),
        nullable=False, index=True,
    )
    presentation_item_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("presentation_items.id", name="fk_item_feedback_presentation_item"),
        nullable=False, index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        CHAR(36), nullable=False, index=True, comment="操作者(合并迁入: 移除 simulated_actor FK)"
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    feedback_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DischargeInstruction(Base, TimestampMixin):
    """出院交代表。"""

    __tablename__ = "discharge_instructions"
    __table_args__ = (
        UniqueConstraint("inpatient_record_id", "instruction_version", name="uq_discharge_instruction_version"),
        {"comment": "出院交代表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="出院交代UUID主键")
    inpatient_record_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_records.id", name="fk_discharge_instruction_inpatient_record"),
        nullable=False, index=True,
    )
    instruction_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    instruction_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    confirm_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ManualIntervention(Base, TimestampMixin):
    """人工补位记录表。"""

    __tablename__ = "manual_interventions"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_manual_intervention_actor_idempotency"),
        {"comment": "人工补位记录表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="人工干预UUID主键")
    handoff_context_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("handoff_contexts.id", name="fk_manual_intervention_handoff_context"),
        nullable=False, index=True,
    )
    related_feedback_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("item_feedbacks.id", name="fk_manual_intervention_feedback"),
        nullable=True,
    )
    presentation_item_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("presentation_items.id", name="fk_manual_intervention_presentation_item"),
        nullable=True,
    )
    actor_id: Mapped[str] = mapped_column(
        CHAR(36), nullable=False, index=True, comment="操作者(合并迁入: 移除 simulated_actor FK)"
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    intervention_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AuditLog(Base, TimestampMixin):
    """不随业务对象级联删除的审计事实。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('patient', 'family', 'caregiver', 'doctor', 'coordinator', 'supervisor', 'system')",
            name="ck_audit_log_actor_role",
        ),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="审计UUID主键")
    actor_id: Mapped[str | None] = mapped_column(
        CHAR(36), nullable=True, index=True, comment="操作者(合并迁入: 移除 simulated_actor FK)"
    )
    actor_role: Mapped[AuditActorRole] = mapped_column(
        SQLEnum(
            AuditActorRole,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            length=16,
        ),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_record_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    action_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class CurrentCondition(Base, TimestampMixin):
    """每日病情记录表。"""

    __tablename__ = "current_conditions"
    __table_args__ = (
        UniqueConstraint("inpatient_record_id", "record_date", name="uq_current_condition_record_date"),
        {"comment": "每日病情记录表"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment="病情记录UUID主键")
    inpatient_record_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("inpatient_records.id", name="fk_current_condition_inpatient_record"),
        nullable=False, index=True,
    )
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    condition_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vital_signs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ============================================================================
# 数据库初始化
# ============================================================================


async def init_db() -> None:
    """初始化数据库表结构。"""
    from .main import async_engine

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
