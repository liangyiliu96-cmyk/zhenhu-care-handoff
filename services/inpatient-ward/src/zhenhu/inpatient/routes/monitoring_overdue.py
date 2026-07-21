"""待上报提醒 — GET /monitoring/overdue
检测哪些患者的生命体征超时未报，提醒护士。
纯 state_store 读取，按模板 monitoring_interval_hours 对比。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overdue")
async def get_overdue_monitoring(request: Request):
    """返回所有体征超时未上报的患者列表。

    根据各病种模板的 monitoring_interval_hours 计算超时。
    未设置间隔的默认 4 小时。
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    overdue = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue

        vs = state.get("vital_signs", []) or []
        tpl = state.get("disease_template", {}) or {}
        interval_hours = tpl.get("monitoring_interval_hours")

        if not interval_hours:
            interval_hours = 4  # 默认 4h

        # 找最近一次有 timestamp 的体征
        last_time = None
        for v in reversed(vs):
            ts_val = v.get("timestamp")
            if ts_val:
                last_time = ts_val
                break

        if not last_time:
            # 无时间戳 → 从 state_store 时间推算
            last_time_ts = ts
            hours_elapsed = (now - last_time_ts) / 3600
        else:
            try:
                from datetime import datetime
                last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
                hours_elapsed = (now - last_dt.timestamp()) / 3600
            except Exception:
                last_time_ts = ts
                hours_elapsed = (now - last_time_ts) / 3600

        if hours_elapsed <= interval_hours:
            continue  # 未超时

        p_data = state.get("patient_data", {}) or {}

        overdue.append({
            "patient_id": pid,
            "state_version": state.get("state_version", 0),
            "name": p_data.get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "unknown"),
            "department": tpl.get("department", "未知"),
            "risk_level": state.get("risk_level"),
            "alert_count": len(state.get("clinical_alerts", []) or []),
            "monitoring_interval_hours": interval_hours,
            "hours_since_last_vs": round(hours_elapsed, 1),
            "overdue_by_hours": round(hours_elapsed - interval_hours, 1),
            "last_vs_values": {
                k: vs[-1].get(k) for k in ("systolic_mmhg", "diastolic_mmhg", "spo2", "heart_rate", "temperature")
                if vs and vs[-1].get(k) is not None
            },
            "phase": state.get("phase"),
        })

    overdue.sort(key=lambda p: -p["overdue_by_hours"])

    return UnifiedResponse(data={
        "total": len(overdue),
        "critical_overdue": sum(1 for p in overdue if p["overdue_by_hours"] > 2),
        "patients": overdue,
    })
