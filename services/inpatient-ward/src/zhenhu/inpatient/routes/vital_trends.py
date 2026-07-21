"""患者体征趋势 — GET /inpatient/{id}/vital-trends

纯读 state_store，零 LLM 调用。按时间排序的体征测量数据，
每个指标独立序列，自动计算趋势方向。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["trends"])


def _require_patient_read_access(request: Request, patient_id: str) -> None:
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc

_METRICS: dict[str, str] = {
    "systolic": "systolic_mmhg",
    "diastolic": "diastolic_mmhg",
    "heart_rate": "heart_rate",
    "spo2": "spo2",
    "temperature": "temperature",
    "respiratory_rate": "respiratory_rate",
    "weight": "weight",
}

_UNITS: dict[str, str] = {
    "systolic": "mmHg",
    "diastolic": "mmHg",
    "heart_rate": "bpm",
    "spo2": "%",
    "temperature": "°C",
    "respiratory_rate": "次/分",
    "weight": "kg",
}


def _trend_direction(values: list[float]) -> str:
    """计算趋势: rising/falling/stable/insufficient"""
    nums = [v for v in values if v is not None]
    if len(nums) < 2:
        return "insufficient"
    first_half = sum(nums[: len(nums) // 2]) / max(1, len(nums) // 2)
    second_half = sum(nums[len(nums) // 2 :]) / max(1, len(nums) - len(nums) // 2)
    if second_half > first_half * 1.03:
        return "rising"
    elif second_half < first_half * 0.97:
        return "falling"
    return "stable"


@router.get("/{patient_id}/vital-trends")
async def get_vital_trends(
    patient_id: str,
    request: Request,
    limit: int = Query(20, ge=2, le=100),
):
    """返回患者体征指标的趋势数据。"""
    _require_patient_read_access(request, patient_id)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={
            "code": "NOT_FOUND",
            "message": f"未找到: {patient_id}",
        })

    vs = (state.get("vital_signs") or [])[-limit:]

    trends: dict = {}
    for metric_name, field in _METRICS.items():
        values: list[dict] = []
        for idx, v in enumerate(vs):
            val = v.get(field)
            if val is not None:
                values.append({
                    "value": val,
                    "timestamp": v.get("timestamp", ""),
                    "round": v.get("round", idx + 1),
                })
        if values:
            raw_vals = [item["value"] for item in values]
            trends[metric_name] = {
                "unit": _UNITS.get(metric_name, ""),
                "latest": raw_vals[-1],
                "min": min(raw_vals),
                "max": max(raw_vals),
                "avg": round(sum(raw_vals) / len(raw_vals), 1),
                "direction": _trend_direction(raw_vals),
                "data": values,
            }

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "total_measurements": len(vs),
        "trends": trends,
    })
