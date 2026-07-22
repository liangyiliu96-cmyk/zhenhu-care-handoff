"""FHIR 操作 API 端点。

POST /fhir/Consent              — 创建患者同意记录
POST /fhir/Observation          — 创建体征/检验 Observation
POST /fhir/Condition            — 创建诊断 Condition
POST /fhir/AuditEvent           — 创建审计事件（INSERT-only）
POST /fhir/MedicationRequest    — 创建用药申请
GET  /fhir/AuditEvent           — 查询审计事件
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.fhir.models import (
    Consent,
    Condition,
    Encounter,
    FHIRAuditEvent,
    MedicationRequest,
    Observation,
    Patient,
    get_session,
)
from zhenhu.fhir.schemas import (
    AuditEventAgent,
    AuditEventAgentWho,
    AuditEventBundleEntry,
    AuditEventBundleResponse,
    AuditEventCreateRequest,
    AuditEventEntity,
    AuditEventEntityReference,
    AuditEventResource,
    AuditEventType,
    ConditionCreateRequest,
    ConsentCreateRequest,
    ConsentCreateResponse,
    FhirCreateResponse,
    MedicationRequestCreateRequest,
    ObservationCreateRequest,
    UnifiedResponse,
)

router = APIRouter(prefix="/fhir", tags=["FHIR Operations"])


# ============================================================================
# 辅助函数
# ============================================================================


def _get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


def _get_actor(request: Request) -> str:
    """从请求头提取操作人角色（默认 doctor）。"""
    return request.headers.get("X-User-Role", "doctor")


async def _record_audit(
    session: AsyncSession,
    patient_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
) -> None:
    """记录 FHIR 访问审计事件。"""
    audit = FHIRAuditEvent(
        patient_id=patient_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
    )
    session.add(audit)
    await session.flush()


# ============================================================================
# 端点
# ============================================================================


@router.post("/Consent", status_code=201)
async def create_consent(
    body: ConsentCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[ConsentCreateResponse]:
    """创建患者知情同意记录。

    对照接口契约 §4.3。

    Args:
        body: Consent 创建请求体，包含 patient_id、scope、status、provision。

    Returns:
        UnifiedResponse[ConsentCreateResponse]: 创建的同意记录摘要。

    Raises:
        HTTPException 404: 患者不存在。
        HTTPException 422: 参数校验失败。
    """
    request_id = _get_request_id(request)
    actor = _get_actor(request)

    # 校验患者存在
    result = await session.execute(
        select(Patient).where(Patient.patient_id == body.patient_id)
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": f"患者不存在: {body.patient_id}",
                "details": {"patient_id": body.patient_id},
            },
        )

    # 构造 granted_to 文本
    granted_to = None
    if body.provision and body.provision.purpose:
        granted_to = f"purpose={body.provision.purpose}"

    # 创建 Consent 记录
    consent = Consent(
        patient_id=body.patient_id,
        scope=body.scope,
        status=body.status,
        granted_to=granted_to,
    )
    session.add(consent)
    await session.flush()

    # 记录审计
    await _record_audit(
        session, body.patient_id, "Consent", consent.consent_id, "C", actor
    )
    await session.commit()

    data = ConsentCreateResponse(consent_id=consent.consent_id, status=consent.status or "active")
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.get("/AuditEvent")
async def get_audit_events(
    patient: str = Query(..., description="患者 ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[AuditEventBundleResponse]:
    """查询 FHIR 访问审计事件。

    对照接口契约 §4.4。
    按患者 ID 过滤，返回 Bundle 包裹的 AuditEvent 列表，支持分页。

    Args:
        patient: 患者 ID（必填）。
        page: 页码，从 1 开始。
        size: 每页条数，最大 100。

    Returns:
        UnifiedResponse[AuditEventBundleResponse]: AuditEvent Bundle 响应。

    Raises:
        HTTPException 404: 患者不存在。
    """
    request_id = _get_request_id(request)
    actor = _get_actor(request)

    # 校验患者存在
    result = await session.execute(
        select(Patient).where(Patient.patient_id == patient)
    )
    patient_obj = result.scalar_one_or_none()

    if patient_obj is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": f"患者不存在: {patient}",
                "details": {"patient_id": patient},
            },
        )

    # 查询总数
    count_result = await session.execute(
        select(func.count(FHIRAuditEvent.id)).where(
            FHIRAuditEvent.patient_id == patient
        )
    )
    total = count_result.scalar_one()

    # 分页查询
    offset = (page - 1) * size
    audit_result = await session.execute(
        select(FHIRAuditEvent)
        .where(FHIRAuditEvent.patient_id == patient)
        .order_by(FHIRAuditEvent.occurred_at.desc())
        .offset(offset)
        .limit(size)
    )
    audit_events = audit_result.scalars().all()

    # 记录本次查询审计
    await _record_audit(session, patient, "AuditEvent", patient, "R", actor)
    await session.commit()

    # 构造响应
    entries: list[AuditEventBundleEntry] = []
    for ae in audit_events:
        resource = AuditEventResource(
            resourceType="AuditEvent",
            id=ae.audit_id,
            type=AuditEventType(code=ae.action or "R"),
            entity=[
                AuditEventEntity(
                    reference=AuditEventEntityReference(
                        reference=f"{ae.entity_type}/{ae.entity_id}"
                    )
                )
            ],
            agent=[
                AuditEventAgent(
                    who=AuditEventAgentWho(display=ae.actor)
                )
            ],
            recorded=ae.occurred_at.isoformat() if ae.occurred_at else None,
        )
        entries.append(AuditEventBundleEntry(resource=resource))

    data = AuditEventBundleResponse(resourceType="Bundle", entry=entries)
    return UnifiedResponse(request_id=request_id, data=data, error=None)


# ============================================================================
# Observation / Condition / AuditEvent / MedicationRequest POST 端点
# (对接 inpatient-ward fhir_sync 模块)
# ============================================================================


def _extract_patient_id(subject_reference: str) -> str:
    """从 'Patient/xxx' 引用中提取 patient_id。"""
    if "/" in subject_reference:
        return subject_reference.split("/", 1)[1]
    return subject_reference


def _code_display(payload: dict) -> str:
    """从 coding 字典中提取 display 文本。"""
    coding_list = payload.get("coding", [])
    if not coding_list:
        coding_list = [payload] if isinstance(payload, dict) else []
    for entry in coding_list:
        if isinstance(entry, dict) and entry.get("display"):
            return entry["display"]
    return payload.get("text", "")


async def _ensure_patient(session: AsyncSession, patient_id: str) -> Patient | None:
    """查找或创建患者记录（fhir-adapter 侧）。"""
    result = await session.execute(
        select(Patient).where(Patient.patient_id == patient_id)
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        # 如果不存在，创建最小 Patient 记录
        patient = Patient(patient_id=patient_id, name=patient_id, gender="unknown")
        session.add(patient)
        await session.flush()
    return patient


@router.post("/Observation", status_code=201)
async def create_observation(
    body: ObservationCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[FhirCreateResponse]:
    """接收 inpatient-ward 体征/PE发现，创建 FHIR Observation。

    对接: inpatient-ward → agent/fhir_sync.py → sync_observation()
    """
    patient_id = _extract_patient_id(body.subject.reference)
    actor = request.headers.get("X-User-Role", "system")
    request_id = getattr(request.state, "request_id", "unknown")

    patient = await _ensure_patient(session, patient_id)
    display = _code_display(body.code)
    value = body.valueQuantity.get("value") if body.valueQuantity else None
    unit = body.valueQuantity.get("unit", "") if body.valueQuantity else ""

    obs = Observation(
        patient_id=patient.patient_id,
        code="auto",
        display=display or "vital_sign",
        value=str(value) if value is not None else None,
        unit=unit,
    )
    session.add(obs)
    await session.flush()

    await _record_audit(session, patient.patient_id, "Observation", obs.observation_id, "C", actor)
    await session.commit()

    return UnifiedResponse(
        request_id=request_id,
        data=FhirCreateResponse(resource_id=obs.observation_id, resource_type="Observation"),
    )


@router.post("/Condition", status_code=201)
async def create_condition(
    body: ConditionCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[FhirCreateResponse]:
    """接收 inpatient-ward DDx/诊断，创建 FHIR Condition。

    对接: inpatient-ward → agent/fhir_sync.py → sync_condition()
    """
    patient_id = _extract_patient_id(body.subject.reference)
    actor = request.headers.get("X-User-Role", "system")
    request_id = getattr(request.state, "request_id", "unknown")

    patient = await _ensure_patient(session, patient_id)
    display = _code_display(body.code)
    code = ""
    coding = body.code.get("coding", [])
    if coding and isinstance(coding[0], dict):
        code = coding[0].get("code", "")

    condition = Condition(
        patient_id=patient.patient_id,
        code=code,
        display=display or "diagnosis",
        severity="moderate",
    )
    session.add(condition)
    await session.flush()

    await _record_audit(session, patient.patient_id, "Condition", condition.condition_id, "C", actor)
    await session.commit()

    return UnifiedResponse(
        request_id=request_id,
        data=FhirCreateResponse(resource_id=condition.condition_id, resource_type="Condition"),
    )


@router.post("/AuditEvent", status_code=201)
async def create_audit_event(
    body: AuditEventCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[FhirCreateResponse]:
    """接收 inpatient-ward 临床审核动作，创建 FHIR AuditEvent（INSERT-only）。

    对接: inpatient-ward → agent/fhir_sync.py → sync_audit_event()
    幂等: 通过 Idempotency-Key header 去重。
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # 从 entity[0].what.reference 提取 patient_id
    patient_id = "unknown"
    if body.entity and body.entity[0].what:
        ref = body.entity[0].what.get("reference", "")
        patient_id = _extract_patient_id(ref) if ref else "unknown"

    patient = await _ensure_patient(session, patient_id)

    actor = "system"
    if body.agent:
        who = body.agent[0].who
        if who and who.identifier:
            actor = who.identifier.get("value", "system")

    audit = FHIRAuditEvent(
        patient_id=patient.patient_id,
        entity_type="AuditEvent",
        entity_id=request_id,
        action=body.action,
        actor=actor,
    )
    session.add(audit)
    await session.commit()

    return UnifiedResponse(
        request_id=request_id,
        data=FhirCreateResponse(resource_id=audit.audit_id, resource_type="AuditEvent"),
    )


@router.post("/MedicationRequest", status_code=201)
async def create_medication_request(
    body: MedicationRequestCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[FhirCreateResponse]:
    """接收 inpatient-ward 用药申请，创建 FHIR MedicationRequest。

    对接: inpatient-ward 照护管理 → 用药订单创建/更新。
    """
    patient_id = _extract_patient_id(body.subject.reference)
    actor = request.headers.get("X-User-Role", "system")
    request_id = getattr(request.state, "request_id", "unknown")

    patient = await _ensure_patient(session, patient_id)

    medication_display = ""
    dosage = ""
    if body.medicationCodeableConcept:
        medication_display = _code_display(body.medicationCodeableConcept)
    if body.dosageInstruction:
        dosage = str(body.dosageInstruction[0]) if body.dosageInstruction else ""

    med_req = MedicationRequest(
        patient_id=patient.patient_id,
        medication_code="auto",
        medication_display=medication_display or "medication",
        dosage=dosage[:255],
        status=body.status or "active",
    )
    session.add(med_req)
    await session.flush()

    await _record_audit(session, patient.patient_id, "MedicationRequest", med_req.med_request_id, "C", actor)
    await session.commit()

    return UnifiedResponse(
        request_id=request_id,
        data=FhirCreateResponse(resource_id=med_req.med_request_id, resource_type="MedicationRequest"),
    )
