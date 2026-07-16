"""Patient Compartment API 端点。

GET  /fhir/Patient/{patient_id}             — 查询患者资源
GET  /fhir/Patient/{patient_id}/CarePlan   — 查询患者照护计划列表
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.fhir.models import CarePlan, FHIRAuditEvent, Patient, get_session
from zhenhu.fhir.schemas import (
    CarePlanBundleEntry,
    CarePlanBundleResponse,
    CarePlanCategory,
    CarePlanPeriod,
    CarePlanResource,
    PatientIdentifier,
    PatientName,
    PatientResponse,
    UnifiedResponse,
)

router = APIRouter(prefix="/fhir", tags=["Patient Compartment"])


# ============================================================================
# 辅助函数
# ============================================================================


def _get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


def _get_actor(request: Request) -> str:
    """从请求头提取操作人角色（默认 doctor）。"""
    return request.headers.get("X-User-Role", "doctor")


def _mask_name(name: str) -> str:
    """姓名脱敏：取首字 + '**'。"""
    if not name:
        return "TOKEN-***"
    return name[0] + "**"


def _mask_identifier(value: str) -> str:
    """标识符脱敏：前缀 + 哈希简写。"""
    if not value:
        return "TOKEN-***"
    return "TOKEN-" + value[-4:] if len(value) >= 4 else "TOKEN-" + value


async def _record_audit(
    session: AsyncSession,
    patient_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
) -> None:
    """记录 FHIR 访问审计事件（异步写入，不影响响应）。"""
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


@router.get("/Patient/{patient_id}")
async def get_patient(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[PatientResponse]:
    """查询单个 Patient 资源。

    对照接口契约 §4.1。
    所有 PII 字段输出脱敏 token（name→首字+**，identifier→TOKEN-***）。

    Args:
        patient_id: 患者业务 ID。

    Returns:
        UnifiedResponse[PatientResponse]: 脱敏后的 FHIR Patient 资源。

    Raises:
        HTTPException 404: 患者不存在。
    """
    request_id = _get_request_id(request)
    actor = _get_actor(request)

    result = await session.execute(
        select(Patient).where(Patient.patient_id == patient_id)
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": f"患者不存在: {patient_id}",
                "details": {"patient_id": patient_id},
            },
        )

    # 记录审计
    await _record_audit(session, patient_id, "Patient", patient_id, "R", actor)
    await session.commit()

    # 构造脱敏响应
    identifiers_raw: list[str] = []
    if patient.identifiers_json:
        import json
        try:
            parsed = json.loads(patient.identifiers_json)
            if isinstance(parsed, list):
                identifiers_raw = [str(v) for v in parsed]
        except (json.JSONDecodeError, TypeError):
            identifiers_raw = []

    data = PatientResponse(
        resourceType="Patient",
        id=patient.patient_id,
        identifier=[PatientIdentifier(value=_mask_identifier(v)) for v in identifiers_raw],
        name=[PatientName(text=_mask_name(patient.name))],
        gender=patient.gender,
        birthDate=patient.birth_date.isoformat() if patient.birth_date else None,
    )
    return UnifiedResponse(request_id=request_id, data=data, error=None)


@router.get("/Patient/{patient_id}/CarePlan")
async def get_patient_care_plans(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CarePlanBundleResponse]:
    """查询患者照护计划列表。

    对照接口契约 §4.2。
    返回 Bundle 包裹的 CarePlan 资源列表。

    Args:
        patient_id: 患者业务 ID。

    Returns:
        UnifiedResponse[CarePlanBundleResponse]: CarePlan Bundle 响应。

    Raises:
        HTTPException 404: 患者不存在。
    """
    request_id = _get_request_id(request)
    actor = _get_actor(request)

    # 校验患者存在
    result = await session.execute(
        select(Patient).where(Patient.patient_id == patient_id)
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": f"患者不存在: {patient_id}",
                "details": {"patient_id": patient_id},
            },
        )

    # 查询照护计划
    cp_result = await session.execute(
        select(CarePlan).where(CarePlan.patient_id == patient_id)
    )
    care_plans = cp_result.scalars().all()

    # 记录审计
    await _record_audit(session, patient_id, "CarePlan", patient_id, "R", actor)
    await session.commit()

    # 构造响应
    entries: list[CarePlanBundleEntry] = []
    for cp in care_plans:
        category_text = "出院随访" if cp.category == "discharge" else "慢病照护"
        resource = CarePlanResource(
            resourceType="CarePlan",
            id=cp.care_plan_id,
            title=f"{'出院' if cp.category == 'discharge' else '慢病'}随访计划",
            status=cp.status,
            category=[CarePlanCategory(text=category_text)],
            intent=cp.intent,
            period=CarePlanPeriod(
                start=cp.period_start.isoformat() if cp.period_start else None,
                end=cp.period_end.isoformat() if cp.period_end else None,
            ),
        )
        entries.append(CarePlanBundleEntry(resource=resource))

    data = CarePlanBundleResponse(resourceType="Bundle", entry=entries)
    return UnifiedResponse(request_id=request_id, data=data, error=None)
