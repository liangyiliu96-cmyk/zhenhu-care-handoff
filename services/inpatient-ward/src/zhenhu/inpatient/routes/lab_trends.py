"""检验结果趋势 — GET /inpatient/{id}/lab-trends

纯读 state_store，零 LLM 调用。按检验项目分组，
结合 disease_template.lab_reference 判断异常。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse

router = APIRouter(prefix="/inpatient", tags=["trends"])


def _require_patient_read_access(request: Request, patient_id: str) -> None:
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc


@router.get("/{patient_id}/lab-trends")
async def get_lab_trends(patient_id: str, request: Request):
    """返回患者检验结果的趋势数据。"""
    _require_patient_read_access(request, patient_id)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={
            "code": "NOT_FOUND",
            "message": f"未找到: {patient_id}",
        })

    labs = state.get("lab_results") or []
    tpl = state.get("disease_template") or {}
    lab_refs = tpl.get("lab_reference") or {}

    # Group by name
    grouped: dict[str, list[dict]] = {}
    for i, lab in enumerate(labs):
        name = lab.get("name", f"unknown_{i}")
        if name not in grouped:
            grouped[name] = []
        try:
            val = float(lab.get("value", 0))
        except (ValueError, TypeError):
            val = None
        ref = lab_refs.get(name, {})
        is_abnormal = False
        if val is not None and ref:
            lo, hi = ref.get("low"), ref.get("high")
            if (lo is not None and val < lo) or (hi is not None and val > hi):
                is_abnormal = True
        grouped[name].append({
            "value": val,
            "unit": lab.get("unit", ""),
            "ref_range": f"{ref.get('low', '?')}-{ref.get('high', '?')}" if ref else None,
            "is_abnormal": is_abnormal,
            "index": i,
        })

    summary: dict = {}
    for name, items in grouped.items():
        vals = [item["value"] for item in items if item["value"] is not None]
        if vals:
            summary[name] = {
                "unit": items[0]["unit"],
                "ref_range": items[0]["ref_range"],
                "latest": vals[-1],
                "min": min(vals),
                "max": max(vals),
                "abnormal_count": sum(1 for item in items if item["is_abnormal"]),
                "total_count": len(items),
                "values": items,
            }

    return UnifiedResponse(data={
        "patient_id": patient_id,
        "total_labs": len(labs),
        "lab_trends": summary,
    })
