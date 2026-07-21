"""待审核队列 — GET /reviews/pending
医生打开系统：有哪些患者卡在审核卡点等我来审？
纯 state_store 聚合读取。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/pending")
async def get_pending_reviews(request: Request):
    """返回所有处于 pending_review 状态的患者和审核详情。"""
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    pending = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        pr = state.get("pending_review")
        if not pr:
            continue

        payload = pr.get("payload", {}) if isinstance(pr, dict) else {}
        tpl = state.get("disease_template", {}) or {}

        pending.append({
            "patient_id": pid,
            "name": (state.get("patient_data", {}) or {}).get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "unknown"),
            "review_id": pr.get("review_id", ""),
            "review_type": pr.get("type", "unknown"),
            # The workbench submits this value as expected_version.  Keeping it
            # on the read model prevents the UI from issuing an unprotected
            # clinical review based on a stale queue entry.
            "state_version": state.get("state_version", 0),
            "risk_level": state.get("risk_level"),
            "payload_summary": {
                "chief_complaint": payload.get("chief_complaint", "")[:100],
                "ddx_count": len(payload.get("ddx_list", []) or []),
                "adjustment_count": payload.get("adjustment_count", 0),
                "handoff_count": payload.get("handoff_count", 0),
            },
            "phase": state.get("phase"),
            "template": payload.get("template", ""),
        })

    return UnifiedResponse(data={
        "total": len(pending),
        "by_type": {
            "doctor_confirm": sum(1 for p in pending if p["review_type"] == "doctor_confirm"),
            "med_confirm": sum(1 for p in pending if p["review_type"] == "med_confirm"),
            "discharge_sign": sum(1 for p in pending if p["review_type"] == "discharge_sign"),
        },
        "reviews": pending,
    })
