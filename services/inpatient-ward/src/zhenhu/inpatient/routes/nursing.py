"""护理记录端点 — GET /inpatient/{id}/nursing。

返回患者全部护理记录列表，包括护理措施、给药记录(MAR)、
出入量(I/O)、护理告警。纯读 state_store，零副作用。
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse

logger = logging.getLogger("zhenhu.inpatient")

router = APIRouter(prefix="/inpatient", tags=["nursing"])


@router.get("/{patient_id}/nursing")
async def get_nursing(patient_id: str, request: Request):
    from .state_store import get_state
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    records = state.get("nursing_records") or []
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "total": len(records),
        "records": records,
    })
