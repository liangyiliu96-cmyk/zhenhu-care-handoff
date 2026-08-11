"""Encrypted patient contact storage for post-discharge follow-up."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from ..models import FollowUpContact


class FollowUpContactConfigurationError(RuntimeError):
    pass


class FollowUpContactService:
    async def get(self, patient_id: str) -> dict[str, Any] | None:
        from ..main import async_session_factory

        async with async_session_factory() as session:
            record = await session.get(FollowUpContact, patient_id)
            return self._decode(record) if record else None

    async def summaries(self, patient_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not patient_ids:
            return {}
        from ..main import async_session_factory

        async with async_session_factory() as session:
            records = list(await session.scalars(select(FollowUpContact).where(FollowUpContact.patient_id.in_(patient_ids))))
        return {record.patient_id: self.summary(self._decode(record)) for record in records}

    async def save(self, patient_id: str, payload: dict[str, Any], expected_contact_version: int | None = None) -> dict[str, Any]:
        from ..main import async_session_factory

        async with async_session_factory() as session:
            async with session.begin():
                record = await session.scalar(select(FollowUpContact).where(FollowUpContact.patient_id == patient_id).with_for_update())
                current_version = record.contact_version if record else 0
                if expected_contact_version is not None and expected_contact_version != current_version:
                    raise ValueError("CONTACT_VERSION_CONFLICT")
                consented = bool(payload["follow_up_consent"])
                stored = {
                    "mobile_phone": payload.get("mobile_phone") if consented else None,
                    "alternate_contact_name": payload.get("alternate_contact_name") if consented else None,
                    "alternate_contact_relation": payload.get("alternate_contact_relation") if consented else None,
                    "alternate_contact_phone": payload.get("alternate_contact_phone") if consented else None,
                    "follow_up_consent": consented,
                    "consented_at": datetime.now(timezone.utc).isoformat() if consented else None,
                    "withdrawn_at": None if consented else datetime.now(timezone.utc).isoformat(),
                }
                next_version = current_version + 1
                if record is None:
                    record = FollowUpContact(patient_id=patient_id, encrypted_payload=self._encrypt(stored), consented=consented, preferred_channel=payload.get("preferred_channel") if consented else None, contact_version=next_version)
                    session.add(record)
                else:
                    record.encrypted_payload = self._encrypt(stored)
                    record.consented = consented
                    record.preferred_channel = payload.get("preferred_channel") if consented else None
                    record.contact_version = next_version
            return self._decode(record)

    def summary(self, contact: dict[str, Any] | None) -> dict[str, Any]:
        if not contact or not contact.get("follow_up_consent"):
            return {"has_contact": False, "follow_up_consent": False, "preferred_channel": None, "masked_mobile_phone": None}
        return {"has_contact": bool(contact.get("mobile_phone")), "follow_up_consent": True, "preferred_channel": contact.get("preferred_channel"), "masked_mobile_phone": _mask_phone(contact.get("mobile_phone"))}

    def _decode(self, record: FollowUpContact) -> dict[str, Any]:
        try:
            payload = json.loads(self._fernet().decrypt(record.encrypted_payload.encode("ascii")).decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FollowUpContactConfigurationError("无法解密随访联系方式，请联系系统管理员") from exc
        return {**payload, "preferred_channel": record.preferred_channel, "contact_version": record.contact_version}

    def _encrypt(self, payload: dict[str, Any]) -> str:
        return self._fernet().encrypt(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")

    def _fernet(self) -> Fernet:
        key = os.environ.get("CONTACT_ENCRYPTION_KEY", "").strip()
        if not key and os.environ.get("APP_ENV", "dev").lower() != "production":
            # Development-only stable key: production must inject an independently rotated secret.
            # 注意: 密钥派生必须固定, 不得依赖 DEEPSEEK_API_KEY —— 否则配置 LLM key 后
            # 旧密文(用旧派生 key 加密)将无法解密, 导致随访联系方式 500。
            source = "zhenhu-dev-contact-key"
            key = base64.urlsafe_b64encode(hashlib.sha256(f"zhenhu-dev-contact:{source}".encode()).digest()).decode()
        if not key:
            raise FollowUpContactConfigurationError("CONTACT_ENCRYPTION_KEY is required in production")
        try:
            return Fernet(key.encode())
        except (TypeError, ValueError) as exc:
            raise FollowUpContactConfigurationError("CONTACT_ENCRYPTION_KEY is invalid") from exc


def _mask_phone(value: object) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return f"{digits[:3]}****{digits[-4:]}" if len(digits) >= 7 else None


follow_up_contact_service = FollowUpContactService()
