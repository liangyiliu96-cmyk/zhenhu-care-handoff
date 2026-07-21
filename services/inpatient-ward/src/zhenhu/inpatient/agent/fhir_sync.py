"""node→FHIR 同步 — v1.3 §十二。

将临床数据（体征/PE发现、DDx/诊断、审核动作）同步到 fhir-adapter。
遵循 SKIP_BRIDGE 模式：环境变量 SKIP_BRIDGE=true 时返回 mock 数据，不调 HTTP。
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("zhenhu.inpatient.fhir_sync")

FHIR_BASE_URL = os.environ.get("FHIR_ADAPTER_URL", "http://localhost:8080/fhir")


async def _http_post(endpoint: str, payload: dict, idempotency_key: str | None = None) -> dict:
    """内部 HTTP POST 辅助。"""
    try:
        url = f"{FHIR_BASE_URL.rstrip('/')}{endpoint}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("fhir_sync HTTP POST failed: %s → %s", endpoint, e)
        raise


async def sync_observation(patient_id: str, vital: dict) -> dict:
    """体征/PE发现 → Observation(FHIR)。

    调用 fhir-adapter 的 /Observation 端点。
    SKIP_BRIDGE=true 时返回 mock 数据。
    """
    if os.environ.get("SKIP_BRIDGE", "").lower() == "true":
        return {"id": f"obs-{patient_id}-mock", "status": "mocked"}

    payload = {
        "resourceType": "Observation",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": vital.get("loinc", "auto"),
                "display": vital.get("name", "vital_sign"),
            }],
        },
        "valueQuantity": {
            "value": float(vital.get("value", 0)),
            "unit": vital.get("unit", ""),
        },
    }
    return await _http_post("/Observation", payload)


async def sync_condition(patient_id: str, ddx_item: dict) -> dict:
    """DDx/诊断 → Condition(FHIR)。

    调用 fhir-adapter 的 /Condition 端点。
    SKIP_BRIDGE=true 时返回 mock 数据。
    """
    if os.environ.get("SKIP_BRIDGE", "").lower() == "true":
        return {"id": f"cond-{patient_id}-mock", "status": "mocked"}

    payload = {
        "resourceType": "Condition",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {
            "coding": [{
                "system": "http://hl7.org/fhir/sid/icd-10",
                "code": ddx_item.get("icd10", ""),
                "display": ddx_item.get("diagnosis", ddx_item.get("disease", "")),
            }],
        },
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": "active",
            }],
        },
    }
    return await _http_post("/Condition", payload)


async def sync_audit_event(
    action: str, actor: str, detail: dict, idempotency_key: str | None = None,
) -> dict:
    """审核动作 → FHIRAuditEvent（INSERT-only，不可改）。

    SKIP_BRIDGE=true 时返回 mock 数据。
    """
    if os.environ.get("SKIP_BRIDGE", "").lower() == "true":
        return {"id": f"audit-{actor}-mock", "status": "mocked"}

    payload = {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": "110100",  # Application Activity
        },
        "action": action,
        "agent": [{
            "who": {"identifier": {"value": actor}},
            "requestor": True,
        }],
        "entity": [{
            "what": {"reference": detail.get("patient_ref", "")},
            "detail": [{"type": k, "valueString": json.dumps(v, ensure_ascii=False)}
                       for k, v in detail.items() if k != "patient_ref"],
        }],
    }
    return await _http_post("/AuditEvent", payload, idempotency_key=idempotency_key)
