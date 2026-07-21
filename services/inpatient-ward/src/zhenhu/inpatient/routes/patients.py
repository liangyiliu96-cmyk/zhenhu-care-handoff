"""患者列表端点 — GET /patients
医生按状态/风险/病种筛选患者，支持搜索。
纯 state_store 聚合读取。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("")
async def list_patients(
    request: Request,
    phase: str | None = Query(None, description="筛选阶段: admission/monitoring/discharge"),
    risk_level: str | None = Query(None, description="筛选风险: low/medium/high"),
    disease: str | None = Query(None, description="病种筛选，支持部分匹配"),
    search: str | None = Query(None, description="患者姓名搜索，支持部分匹配"),
    sort: str = Query("risk", description="排序: risk/phase/name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="分页偏移量"),
):
    """按条件筛选患者列表，支持排序和搜索。"""
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    patients = []
    from ..services.patient_access import can_access_patient_state
    user = getattr(request.state, "user_info", {})

    for pid, (ts, state) in list(_store.items()):
        if now - ts > ttl or not isinstance(state, dict):
            continue
        if not can_access_patient_state(state, user):
            continue

        p_data = state.get("patient_data", {}) or {}
        p_name = p_data.get("name", "")
        p_phase = state.get("phase", "unknown")
        p_risk = state.get("risk_level", "unknown")
        tpl = state.get("disease_template", {}) or {}
        p_disease = tpl.get("name") or tpl.get("disease_id", "unknown")

        # 筛选
        if phase and p_phase != phase:
            continue
        if risk_level and p_risk != risk_level:
            continue
        if disease and disease.lower() not in p_disease.lower():
            continue
        if search and search.lower() not in p_name.lower() and search.lower() not in pid.lower():
            continue

        # 最新体征摘要
        vs = state.get("vital_signs", []) or []
        latest = vs[-1] if vs else {}

        # 待审核状态
        has_pending = bool(state.get("pending_review"))
        pending_type = (state.get("pending_review") or {}).get("type")

        patients.append({
            "patient_id": pid,
            "name": p_name or pid[:10],
            "disease": p_disease,
            "phase": p_phase,
            "risk_level": p_risk,
            "round_count": state.get("round_count", 0),
            "discharge_decision": state.get("discharge_decision"),
            "has_pending_review": has_pending,
            "pending_review_type": pending_type,
            "alert_count": len(state.get("clinical_alerts", []) or []),
            "latest_vs": {
                "systolic": latest.get("systolic_mmhg"),
                "diastolic": latest.get("diastolic_mmhg"),
                "heart_rate": latest.get("heart_rate"),
                "spo2": latest.get("spo2"),
                "temperature": latest.get("temperature"),
            },
            "document_count": len(state.get("document_chain", [])),
            "_updated_at": ts,
        })

    # 排序
    if sort == "phase":
        phase_order = {"admission": 0, "monitoring": 1, "discharge": 2, "confirm": 3}
        patients.sort(key=lambda p: (phase_order.get(p["phase"], 99), -p["_updated_at"], p["name"]))
    elif sort == "name":
        patients.sort(key=lambda p: (p["name"], -p["_updated_at"]))
    else:  # risk (default)
        risk_order = {"high": 0, "medium": 1, "low": 2}
        patients.sort(key=lambda p: (
            0 if p["has_pending_review"] else 1,
            risk_order.get(p["risk_level"], 3),
            -p["_updated_at"],
        ))

    page = patients[offset:offset + limit]
    for patient in page:
        patient.pop("_updated_at", None)

    return UnifiedResponse(data={
        "total": len(patients),
        "filters": {"phase": phase, "risk_level": risk_level, "disease": disease, "search": search},
        "patients": page,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned": len(page),
            "has_more": offset + limit < len(patients),
        },
    })
