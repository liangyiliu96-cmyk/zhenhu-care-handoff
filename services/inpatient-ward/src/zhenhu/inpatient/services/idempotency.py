"""Durable request-idempotency reservation and replay primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import IdempotencyRecord


class IdempotencyKeyConflictError(Exception):
    """Raised when a key is reused for a different request payload."""


@dataclass(frozen=True)
class IdempotencyReservation:
    record: IdempotencyRecord
    is_new: bool


async def reserve_request(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    fingerprint: str,
) -> IdempotencyReservation:
    """Reserve a request key once across all application instances."""
    record = IdempotencyRecord(
        id=str(uuid4()),
        scope=scope,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        status="processing",
    )
    session.add(record)
    try:
        await session.commit()
        return IdempotencyReservation(record=record, is_new=True)
    except IntegrityError:
        await session.rollback()

    existing = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if existing is None:
        raise RuntimeError("idempotency reservation disappeared after uniqueness conflict")
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyKeyConflictError(key)
    return IdempotencyReservation(record=existing, is_new=False)


async def complete_request(
    session: AsyncSession,
    *,
    record_id: str,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    record = await session.get(IdempotencyRecord, record_id)
    if record is None:
        raise RuntimeError("idempotency reservation was deleted before completion")
    record.status = "completed"
    record.response_status = response_status
    record.response_body = response_body
    await session.commit()


async def abandon_request(session: AsyncSession, *, record_id: str) -> None:
    record = await session.get(IdempotencyRecord, record_id)
    if record is not None and record.status == "processing":
        await session.delete(record)
        await session.commit()
