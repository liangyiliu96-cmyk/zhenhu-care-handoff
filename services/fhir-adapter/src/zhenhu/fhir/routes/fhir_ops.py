"""FHIR 操作 API 端点。

POST /fhir/Consent              — 创建患者同意记录
GET  /fhir/AuditEvent           — 查询审计事件
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.fhir.models import Consent, FHIRAuditEvent, Patient, get_session
from zhenhu.fhir.schemas import (
    AuditEventAgent,
    AuditEventAgentWho,
    AuditEventBundleEntry,
    AuditEventBundleResponse,
    AuditEventEntity,
    AuditEventEntityReference,
    AuditEventResource,
    AuditEventType,
    ConsentCreateRequest,
    ConsentCreateResponse,
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
