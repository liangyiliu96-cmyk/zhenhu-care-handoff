"""Patient-scoped AI coordination draft endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from .route_schemas import WorkflowBriefRequest

router = APIRouter(prefix="/inpatient", tags=["workflow-briefs"])

_WORKFLOW_BRIEF_KINDS = {"mdt", "follow_up", "transfer"}
_GENERATABLE_BY_ROLE = {
    "doctor": _WORKFLOW_BRIEF_KINDS,
    # 随访脚本是低风险的沟通草稿；不会创建任务、外发消息或改变医嘱。
    "nurse": {"follow_up"},
}


def _require_access(request: Request, patient_id: str, *, write: bool) -> dict:
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    user = getattr(request.state, "user_info", {}) or {}
    try:
        require_patient_access(patient_id, user)
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc
    return user


@router.get("/{patient_id}/workflow-briefs")
async def get_workflow_briefs(patient_id: str, request: Request):
    _require_access(request, patient_id, write=False)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    return UnifiedResponse(data={"patient_id": patient_id, "state_version": state.get("state_version", 0), "briefs": state.get("workflow_briefs", {}) or {}})


@router.post("/{patient_id}/workflow-briefs/{kind}")
async def generate_workflow_brief(patient_id: str, kind: str, body: WorkflowBriefRequest, request: Request):
    user = _require_access(request, patient_id, write=True)
    if kind not in _WORKFLOW_BRIEF_KINDS:
        raise HTTPException(status_code=422, detail="不支持的协同草稿类型")
    if kind not in _GENERATABLE_BY_ROLE.get(user.get("role"), set()):
        raise HTTPException(status_code=403, detail="当前角色无权生成该协同草稿")
    from ..agent.workflow_briefs import build_workflow_brief
    from ..services.patient_state import PatientNotFoundError, patient_state_service

    async def planner(state: dict, _loop) -> dict:
        brief = await build_workflow_brief(state, kind)
        briefs = dict(state.get("workflow_briefs") or {})
        briefs[kind] = brief
        return {**state, "workflow_briefs": briefs}

    try:
        await patient_state_service.plan_clinical(
            request,
            patient_id,
            lambda _state: None,
            action_type="workflow_brief_generated",
            detail={"kind": kind, "generated_by": user.get("actor_id")},
            idempotency_scope=f"workflow_brief_{kind}",
            planner=planner,
            expected_version=body.expected_version,
        )
        state = await patient_state_service.read(patient_id)
    except PatientNotFoundError:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到: {patient_id}"})
    return UnifiedResponse(data={"patient_id": patient_id, "state_version": state.get("state_version", 0), "brief": (state.get("workflow_briefs") or {}).get(kind, {})})
