"""Management-only operations for the optional Neo4j clinical evidence graph."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse
from ..services.management_access import require_management_operation


router = APIRouter(prefix="/admin/evidence-graph", tags=["evidence-graph"])


@router.get("/status")
async def evidence_graph_status(request: Request):
    require_management_operation(request, "evidence_graph_rebuild", write=False)
    from ..services.evidence_graph import evidence_graph_status as get_status

    return UnifiedResponse(data=get_status())


@router.post("/rebuild")
async def rebuild_evidence_graph(request: Request):
    require_management_operation(request, "evidence_graph_rebuild")
    from ..services.evidence_graph import EvidenceGraphUnavailable, rebuild_evidence_graph as rebuild

    try:
        result = rebuild()
    except EvidenceGraphUnavailable as exc:
        raise HTTPException(status_code=503, detail={"message": "Evidence graph is unavailable", "error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"message": "Evidence graph rebuild failed", "error": type(exc).__name__}) from exc
    from ..agent.audit import write_management_audit_event

    audit_id = await write_management_audit_event(action_type="evidence_graph_rebuilt", detail=result, request=request)
    return UnifiedResponse(data={**result, "audit_id": audit_id})


@router.get("/diseases/{disease_id}")
async def get_disease_evidence(request: Request, disease_id: str, focus: str = "", limit: int = 12):
    require_management_operation(request, "evidence_graph_rebuild", write=False)
    from ..services.evidence_graph import EvidenceGraphUnavailable, disease_evidence

    try:
        return UnifiedResponse(data=disease_evidence(disease_id, focus=focus, limit=limit))
    except EvidenceGraphUnavailable as exc:
        raise HTTPException(status_code=503, detail={"message": "Evidence graph is unavailable", "error": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc


@router.get("/diseases/{disease_id}/visualization")
async def get_disease_visualization(request: Request, disease_id: str, focus: str = "", limit: int = 12):
    """Return a bounded, browser-safe projection of the Neo4j evidence subgraph."""
    require_management_operation(request, "evidence_graph_rebuild", write=False)
    from ..services.evidence_graph import EvidenceGraphUnavailable, disease_graph_visualization

    try:
        return UnifiedResponse(data=disease_graph_visualization(disease_id, focus=focus, limit=limit))
    except EvidenceGraphUnavailable as exc:
        raise HTTPException(status_code=503, detail={"message": "Evidence graph is unavailable", "error": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
