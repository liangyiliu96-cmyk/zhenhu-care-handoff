"""路由请求/响应 Pydantic Schema。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VitalSignsRequest(BaseModel):
    """体征数据上报请求。包含血压、心率、血氧、体温及附加上下文。"""
    timestamp: str | None = None
    blood_pressure: str | None = None
    systolic_mmhg: int | None = None
    diastolic_mmhg: int | None = None
    heart_rate: int | None = None
    spo2: int | None = None
    temperature: float | None = None
    additional: dict | None = None
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class LabResultsRequest(BaseModel):
    """检验结果上报请求。含检验项名称、数值、单位。"""
    name: str
    value: str | float
    unit: str = ""
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class AlertLifecycleRequest(BaseModel):
    """Optional optimistic-lock value for an alert lifecycle mutation."""
    expected_version: int | None = Field(default=None, ge=1)


class ReviewRequest(BaseModel):
    """医生审核决策请求（Batch 0 → P1 扩展）。"""
    review_type: str = Field(..., description="doctor_confirm|med_confirm|discharge_sign")
    decision: str = Field(..., description="approved|rejected|signed")
    comment: str = Field(default="", description="审核备注")
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")

    # ★ P1a 新增: 入院编辑
    edits: "EditPayload | None" = Field(default=None, description="入院确认时的临床草稿编辑")

    # ★ P1b 新增: 出院编辑 + 拒签原因
    handoff_edits: "list[HandoffEditItem] | None" = Field(default=None)
    reject_reason: str | None = Field(default=None, description="拒签原因，如'BP未稳定'")

    # ★ P1c 新增: 住院期医生决策
    doctor_action: str | None = Field(default=None, description="continue|adjust|new_labs|discharge")
    doctor_orders: dict | None = Field(default=None)


# ── v1.1 P1: 医生编辑模型 ──

class DDxEditItem(BaseModel):
    """DDx 单条编辑操作。"""
    action: str = Field(..., description="add|remove|reorder")
    diagnosis: str | None = Field(default=None, description="remove 时的诊断名")
    item: dict | None = Field(default=None, description="add 时的诊断条目 {diagnosis, icd10, likelihood, key_findings}")
    new_order: list[str] | None = Field(default=None, description="reorder 时的新顺序诊断名列表")


class HandoffEditItem(BaseModel):
    """Handoff 单条编辑操作。"""
    action: str = Field(..., description="add|remove|edit")
    index: int | None = Field(default=None, description="remove/edit 的目标索引")
    item: dict | None = Field(default=None, description="add/edit 时的条目内容 {type, content}")


class EditPayload(BaseModel):
    """医生编辑负载（卡点①）。"""
    hpi_narrative: str | None = Field(default=None)
    pe_narrative: str | None = Field(default=None)
    chief_complaint: str | None = Field(default=None)
    ddx_edits: list[DDxEditItem] | None = Field(default=None)
    allergies: list[dict] | None = Field(default=None)


# ── v1.3 §七 Batch C2: 录入闭环 Schema ──

class HistoryRequest(BaseModel):
    """病史录入 — CC/HPI/PMH/FH/SH/ROS。

    遵循 SOAP/OLDCARTS 七要素标准。
    """
    chief_complaint: str = Field(default="", description="主诉(CC): 患者原话 + 持续时间")
    hpi_narrative: str | None = Field(default=None, description="现病史叙事段落")
    ros_findings: dict | None = Field(default=None, description="系统回顾发现 {系统名: 发现}")
    allergies: list[dict] = Field(default_factory=list, description="过敏史")
    pmh: dict = Field(default_factory=dict, description="既往史(慢病史/手术史/住院史)")
    fh: dict = Field(default_factory=dict, description="家族史(一级亲属疾病)")
    sh: dict = Field(default_factory=dict, description="社会史(吸烟/饮酒/职业/照护者)")
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")


class PhysicalExamRequest(BaseModel):
    """体格检查录入 — Bates 指南各系统。

    每个系统含视诊/触诊/叩诊/听诊发现。
    """
    vital_signs: dict = Field(default_factory=dict, description="当前生命体征 T/HR/RR/BP/SpO2")
    general: str | None = Field(default=None, description="一般情况: 发育/营养/意识/体位")
    heent: str | None = Field(default=None, description="HEENT: 头/眼/耳/鼻/喉")
    neck: str | None = Field(default=None, description="颈部: JVP/气管/甲状腺/淋巴结")
    chest_lungs: str | None = Field(default=None, description="胸部-肺: 视触叩听/呼吸音/啰音")
    chest_heart: str | None = Field(default=None, description="胸部-心脏: 心界/心音/杂音")
    abdomen: str | None = Field(default=None, description="腹部: 视触叩听/肝脾/压痛")
    extremities: str | None = Field(default=None, description="四肢脊柱: 水肿/畸形/DVT征")
    neurological: str | None = Field(default=None, description="神经系统: 颅神经/肌力/感觉/反射")
    skin: str | None = Field(default=None, description="皮肤: 皮疹/压疮/出血点")
    pe_narrative: str | None = Field(default=None, description="LLM生成的查体叙事段落（可覆盖）")
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")


class NursingRequest(BaseModel):
    """护理记录录入 — MAR/I/O/护理措施。

    与 monitoring 互补：monitoring 判断"能不能出院"，nursing 记录"做了什么护理"。
    """
    vital_signs: dict = Field(default_factory=dict, description="当前生命体征")
    medications_administered: list[dict] = Field(default_factory=list,
                                                  description="给药记录 [{drug, dose, time, route, nurse}]")
    intake_ml: float = Field(default=0.0, description="入量(ml)")
    output_ml: float = Field(default=0.0, description="出量(ml)")
    nursing_actions: str = Field(default="", description="护理措施: 翻身/口腔/导管/伤口/压疮预防")
    alerts: list[str] = Field(default_factory=list, description="护理异常报告")
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")


class NursingTaskCompletionRequest(BaseModel):
    """Complete one server-derived nursing task with optimistic locking."""

    task_type: Literal["vital_signs", "nursing_action", "medication", "checklist"]
    task_key: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=1000)
    expected_version: int = Field(ge=1, description="Patient state version read by the client")


# ── v1.1 P0b: Dashboard Schema ──

class VitalTrendItem(BaseModel):
    """单个体征趋势数据点，用于仪表盘体征趋势图。"""
    timestamp: str = ""
    heart_rate: int | None = None
    blood_pressure: str | None = None
    spo2: int | None = None
    temperature: float | None = None


class AbnormalLabItem(BaseModel):
    """异常检验项，含参考范围对比及偏离方向。"""
    name: str
    value: str
    unit: str = ""
    ref_range: str | None = None


class DashboardResponse(BaseModel):
    """医生仪表盘响应 — 患者临床全景视图。"""
    patient_id: str
    patient_name: str = ""
    state_version: int = 0
    is_on_hold: bool = False
    phase: str
    template_name: str
    template_id: str = ""

    vital_trend: list[VitalTrendItem] = []
    vital_trend_direction: dict = {}
    soap_summary: dict | None = None
    ddx_top3: list[dict] = []
    abnormal_labs: list[AbnormalLabItem] = []
    medication_current: list[dict] = []
    complication_alerts: list[str] = []
    discharge_criteria_status: dict | None = None
    discharge_blockers: list[dict] = []
    nursing_summary: dict = {}
    last_updated: str = ""
    # 医生面板优化: 变化视角
    delta_summary: dict = {}
    medication_journey: list[dict] = []
    pain_gcs_trend: dict = {}
    action_history: list[dict] = []
    ai_recommendation: str = ""
    decision_checklist: list[dict] = []
    discharge_readiness: dict = {}
    icd10_codes: list[dict] = []
    medication_safety: dict = {}
    pending_review_type: str = ""
    pending_review_id: str = ""
    discharge_sign_status: str = ""
    handoff_acknowledged: bool = False
    patient_confirmation_status: str = ""
    patient_confirmation_requirements: list[str] = []
    patient_confirmation_evidence: list[dict] = []
    bridge_status: str = ""
    bridge_error: str = ""


# ── v1.1 P2a: 医生流程控制 Schema ──

class DoctorCommandRequest(BaseModel):
    """医生主动流程控制请求。"""
    action: Literal["discharge", "transfer", "consult", "hold", "resume"] = Field(...)
    target: str | None = Field(default=None, description="transfer 目标科室; consult 目标专科")
    reason: str = Field(default="", description="操作原因")
    context: dict | None = Field(default=None, description="附加上下文")
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")


class DischargeInitiationRequest(BaseModel):
    """Official request body for starting the discharge workflow."""

    reason: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=1, description="客户端读取到的患者状态版本")


class MedicationOrderRequest(BaseModel):
    medication: str = Field(min_length=1, max_length=200)
    dose: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    route: str = Field(default="PO", max_length=50)
    indication: str = Field(default="", max_length=500)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class MedicationOrderStatusRequest(BaseModel):
    status: Literal["active", "held", "discontinued", "cancelled"]
    note: str = Field(default="", max_length=500)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class InvestigationOrderRequest(BaseModel):
    test_name: str = Field(min_length=1, max_length=300)
    priority: Literal["routine", "urgent"] = "routine"
    reason: str = Field(min_length=1, max_length=1000)
    timing: str = Field(default="", max_length=100)
    instructions: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class InvestigationOrderStatusRequest(BaseModel):
    status: Literal["scheduled", "completed", "cancelled"]
    note: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class MDTRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    specialties: list[str] = Field(min_length=1, max_length=10)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class MDTDecisionRequest(BaseModel):
    decision: Literal["accepted", "deferred", "declined"]
    summary: str = Field(default="", max_length=2000)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class EducationAcknowledgementRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    recipient: Literal["patient", "family", "caregiver"]
    teach_back: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class FollowUpTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: str = Field(min_length=1, max_length=100)
    assignee: str | None = Field(default=None, max_length=200)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class FollowUpContactRequest(BaseModel):
    mobile_phone: str | None = Field(default=None, max_length=32)
    alternate_contact_name: str | None = Field(default=None, max_length=100)
    alternate_contact_relation: str | None = Field(default=None, max_length=50)
    alternate_contact_phone: str | None = Field(default=None, max_length=32)
    preferred_channel: Literal["phone", "sms", "wechat"] = "phone"
    follow_up_consent: bool = False
    expected_contact_version: int | None = Field(default=None, ge=0)

    @field_validator("mobile_phone", "alternate_contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("电话号码格式不正确")
        return digits

    @model_validator(mode="after")
    def validate_consent_contact(self):
        if self.follow_up_consent and not self.mobile_phone:
            raise ValueError("取得随访授权后必须登记患者手机号")
        return self


class FollowUpTaskUpdateRequest(BaseModel):
    status: Literal["completed", "cancelled"]
    note: str = Field(default="", max_length=1000)
    expected_version: int | None = Field(default=None, ge=1, description="Patient state version read by the client")


class MedicationActionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medication: str = Field(min_length=1, max_length=200)
    dose: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    route: str = Field(default="PO", max_length=50)
    indication: str = Field(default="", max_length=500)


class InvestigationActionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(min_length=1, max_length=300)
    priority: Literal["routine", "urgent"] = "routine"
    reason: str = Field(min_length=1, max_length=1000)
    timing: str = Field(default="", max_length=100)
    instructions: str = Field(default="", max_length=1000)


class FollowUpActionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    due_at: str = Field(min_length=1, max_length=100)
    assignee: str | None = Field(default=None, max_length=200)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("due_at must be an ISO 8601 datetime") from exc
        return value


class MdtActionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    specialties: list[str] = Field(min_length=1, max_length=10)


class EducationPlanActionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    recipient: Literal["patient", "family", "caregiver"] = "patient"
    key_points: list[str] = Field(default_factory=list, max_length=6)


class AssistantActionDraftCreateRequest(BaseModel):
    draft_type: Literal["medication_order", "investigation_order", "follow_up_task", "mdt_request", "education_plan"]
    payload: dict
    rationale: str = Field(default="", max_length=2000)
    citations: list[dict] = Field(default_factory=list, max_length=20)
    session_id: str = Field(min_length=1, max_length=100)
    source_text: str = Field(min_length=1, max_length=12000)
    expected_version: int = Field(ge=1)


class AssistantActionDraftGenerateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    source_text: str = Field(min_length=1, max_length=12000)
    citations: list[dict] = Field(default_factory=list, max_length=20)
    expected_version: int = Field(ge=1)


class AssistantActionDraftUpdateRequest(BaseModel):
    payload: dict
    rationale: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=1)


class AssistantActionDraftDecisionRequest(BaseModel):
    comment: str = Field(default="", max_length=1000)
    expected_version: int = Field(ge=1)


# ── H10: 出院小结 Schema ──

class DischargeSummaryResponse(BaseModel):
    """出院小结响应 — 主诊断、住院经过、出院用药、随访计划。"""
    patient_id: str
    primary_diagnosis: str = ""
    secondary_diagnoses: list[str] = []
    hospital_course: list[str] = []
    discharge_medications: list[dict] = []
    follow_up_plan: list[dict] = []
    critical_events: list[str] = []
    discharge_decision: str = ""
    handoff_summary: list[dict] = []
    last_updated: str = ""
    narrative: str = ""


# ── #4: 自然语言查询 Schema ──

class QueryRequest(BaseModel):
    """自然语言查询请求。"""
    question: str = Field(min_length=2, max_length=1000, description="医生关于患者临床状态的自然语言问题")

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return value.strip()


class RoundGenerateRequest(BaseModel):
    """Generate a new Agent-assisted SOAP round from current patient facts."""

    expected_version: int = Field(ge=1)


class RoundReviewRequest(BaseModel):
    """Record the doctor's review of one generated round summary."""

    comment: str = Field(default="", max_length=1000)
    expected_version: int = Field(ge=1)


class RoundEditRequest(BaseModel):
    """Doctor-authored revision layered on top of an Agent round draft."""

    subjective: str = Field(default="", max_length=3000)
    objective: str = Field(default="", max_length=3000)
    assessment: str = Field(default="", max_length=3000)
    plan: str = Field(default="", max_length=3000)
    attention: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("subjective", "objective", "assessment", "plan", "attention")
    @classmethod
    def normalize_round_edit(cls, value: str) -> str:
        return value.strip()


class WorkflowBriefRequest(BaseModel):
    expected_version: int = Field(ge=1)
