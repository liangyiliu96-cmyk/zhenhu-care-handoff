"""Pydantic v2 请求/响应 Schema —— fhir-adapter 服务。

定义 FHIR 适配层的入参校验和出参格式，与接口契约 03 §4 对齐。
阶段J审计修复: UnifiedResponse/ErrorDetail 统一迁移至 zhenhu.contracts。
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from zhenhu.contracts import ErrorDetail, UnifiedResponse  # noqa: F401 — 阶段J审计修复; 经本模块再导出


# ============================================================================
# FHIR Patient 资源
# ============================================================================


class PatientIdentifier(BaseModel):
    """患者标识符（脱敏后）。"""

    value: str = Field(..., description="标识符 token 值")


class PatientName(BaseModel):
    """患者姓名（脱敏后）。"""

    text: str = Field(..., description="姓名 token 值")


class PatientResponse(BaseModel):
    """FHIR Patient 资源响应体 —— 对照接口契约 §4.1。

    PII 字段（name, identifier）输出脱敏 token。
    """

    resourceType: str = Field(default="Patient", description="FHIR 资源类型")
    id: str = Field(..., description="患者 ID")
    identifier: list[PatientIdentifier] = Field(default_factory=list, description="脱敏标识符列表")
    name: list[PatientName] = Field(default_factory=list, description="脱敏姓名列表")
    gender: str | None = Field(default=None, description="性别")
    birthDate: str | None = Field(default=None, description="出生日期（YYYY-MM-DD）")


# ============================================================================
# FHIR CarePlan 资源
# ============================================================================


class CarePlanCategory(BaseModel):
    """CarePlan 分类。"""

    text: str = Field(..., description="分类显示文本")


class CarePlanPeriod(BaseModel):
    """CarePlan 时间范围。"""

    start: str | None = Field(default=None, description="起始日期")
    end: str | None = Field(default=None, description="结束日期")


class CarePlanResource(BaseModel):
    """FHIR CarePlan 资源体。"""

    resourceType: str = Field(default="CarePlan", description="FHIR 资源类型")
    id: str = Field(..., description="照护计划 ID")
    title: str = Field(..., description="照护计划标题")
    status: str | None = Field(default=None, description="状态")
    category: list[CarePlanCategory] = Field(default_factory=list, description="分类")
    intent: str | None = Field(default=None, description="意图：plan/order")
    period: CarePlanPeriod | None = Field(default=None, description="时间范围")


class CarePlanBundleEntry(BaseModel):
    """Bundle 中单条 CarePlan 条目。"""

    resource: CarePlanResource = Field(..., description="CarePlan 资源")


class CarePlanBundleResponse(BaseModel):
    """FHIR Bundle 响应 —— 包装多条 CarePlan。

    对照接口契约 §4.2。
    """

    resourceType: str = Field(default="Bundle", description="FHIR 资源类型")
    entry: list[CarePlanBundleEntry] = Field(default_factory=list, description="CarePlan 条目列表")


# ============================================================================
# FHIR Consent
# ============================================================================


class ConsentProvision(BaseModel):
    """Consent 授权条款。"""

    purpose: str | None = Field(default=None, description="授权用途")


class ConsentCreateRequest(BaseModel):
    """创建 Consent 请求体 —— 对照接口契约 §4.3。

    Attributes:
        patient_id: 患者 ID。
        scope: 授权范围。
        status: 同意状态（active 表示有效）。
        provision: 授权条款详情。
    """

    patient_id: str = Field(..., min_length=1, max_length=128, description="患者 ID")
    scope: str = Field(default="patient-privacy-consent", description="授权范围")
    status: str = Field(default="active", pattern=r"^(active|inactive)$", description="同意状态")
    provision: ConsentProvision | None = Field(default=None, description="授权条款")


class ConsentCreateResponse(BaseModel):
    """Consent 创建响应体。"""

    consent_id: str = Field(..., description="同意记录 ID")
    status: str = Field(..., description="同意状态")


# ============================================================================
# FHIR AuditEvent
# ============================================================================


class AuditEventType(BaseModel):
    """AuditEvent 类型。"""

    code: str = Field(..., description="操作代码：C/R/U/D")


class AuditEventEntityReference(BaseModel):
    """被访问实体的 FHIR 引用。"""

    reference: str = Field(..., description="FHIR 引用（如 Patient/PAT-xxx）")


class AuditEventEntity(BaseModel):
    """AuditEvent 实体条目。"""

    reference: AuditEventEntityReference = Field(..., description="实体引用")


class AuditEventAgentWho(BaseModel):
    """操作人标识。"""

    display: str | None = Field(default=None, description="操作人显示名")


class AuditEventAgent(BaseModel):
    """AuditEvent 操作人。"""

    who: AuditEventAgentWho | None = Field(default=None, description="操作人标识")


class AuditEventResource(BaseModel):
    """FHIR AuditEvent 资源体。"""

    resourceType: str = Field(default="AuditEvent", description="FHIR 资源类型")
    id: str = Field(..., description="审计事件 ID")
    type: AuditEventType | None = Field(default=None, description="事件类型")
    entity: list[AuditEventEntity] = Field(default_factory=list, description="涉及的实体")
    agent: list[AuditEventAgent] = Field(default_factory=list, description="操作人")
    recorded: str | None = Field(default=None, description="记录时间（ISO 8601）")


class AuditEventBundleEntry(BaseModel):
    """Bundle 中单条 AuditEvent 条目。"""

    resource: AuditEventResource = Field(..., description="AuditEvent 资源")


class AuditEventBundleResponse(BaseModel):
    """FHIR Bundle 响应 —— 包装多条 AuditEvent。

    对照接口契约 §4.4。
    """

    resourceType: str = Field(default="Bundle", description="FHIR 资源类型")
    entry: list[AuditEventBundleEntry] = Field(default_factory=list, description="AuditEvent 条目列表")


# ============================================================================
# 患者照护视图聚合
# ============================================================================


class PatientCareViewResponse(BaseModel):
    """患者照护视图聚合响应 —— 阶段 0: 患者照护视图聚合。

    Attributes:
        patient: 患者基本信息 {name, gender, age, discharge_to}。
        care_plans: 照护计划列表 [{title, category, status, period}]。
        education: 知识材料引用 [{title, text, source}]。
    """

    patient: dict = Field(default_factory=dict, description="患者基本信息")
    care_plans: list = Field(default_factory=list, description="照护计划列表")
    education: list = Field(default_factory=list, description="知识材料引用")


# ============================================================================
# FHIR Observation / Condition / AuditEvent / MedicationRequest — 写端点
# ============================================================================


class CodingEntry(BaseModel):
    """FHIR Coding 条目。"""
    system: str | None = Field(default=None)
    code: str | None = Field(default=None)
    display: str | None = Field(default=None)


class SubjectReference(BaseModel):
    """FHIR 资源主体引用。"""
    reference: str = Field(..., description="如 Patient/pat-001")


class ObservationCreateRequest(BaseModel):
    """创建 Observation 请求体 —— 对接 inpatient-ward fhir_sync。"""
    resourceType: str = Field(default="Observation")
    subject: SubjectReference
    code: dict = Field(default_factory=dict, description="coding 字典，含 system/code/display")
    valueQuantity: dict | None = Field(default=None, description="{value, unit}")


class ConditionCreateRequest(BaseModel):
    """创建 Condition 请求体 —— 对接 inpatient-ward fhir_sync。"""
    resourceType: str = Field(default="Condition")
    subject: SubjectReference
    code: dict = Field(default_factory=dict, description="coding 字典，含 system/code/display")
    clinicalStatus: dict | None = Field(default=None)


class AuditEventAgentWhoSimple(BaseModel):
    identifier: dict = Field(default_factory=dict, description="{value: actor}")


class AuditEventAgentSimple(BaseModel):
    who: AuditEventAgentWhoSimple | None = Field(default=None)
    requestor: bool = Field(default=True)


class AuditEventEntityDetail(BaseModel):
    type: str = ""
    valueString: str = ""


class AuditEventEntitySimple(BaseModel):
    what: dict = Field(default_factory=dict, description="{reference: ...}")
    detail: list[AuditEventEntityDetail] = Field(default_factory=list)


class AuditEventCreateRequest(BaseModel):
    """创建 AuditEvent 请求体 —— 对接 inpatient-ward fhir_sync。"""
    resourceType: str = Field(default="AuditEvent")
    type: dict = Field(default_factory=dict)
    action: str = Field(default="C")
    agent: list[AuditEventAgentSimple] = Field(default_factory=list)
    entity: list[AuditEventEntitySimple] | None = Field(default=None)


class MedicationRequestCreateRequest(BaseModel):
    """创建 MedicationRequest 请求体 —— 对接 inpatient-ward。"""
    resourceType: str = Field(default="MedicationRequest")
    subject: SubjectReference
    medicationCodeableConcept: dict | None = Field(default=None)
    dosageInstruction: list | None = Field(default=None)
    status: str = Field(default="active")


class FhirCreateResponse(BaseModel):
    """通用 FHIR 创建响应。"""
    resource_id: str
    resource_type: str
    status: str = "created"
