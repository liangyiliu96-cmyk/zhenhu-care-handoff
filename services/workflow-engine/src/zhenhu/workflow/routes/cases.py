"""病例相关 API 端点。

GET  /cases/{case_id}          — 查询病例概览
POST /cases                 — 创建病例
POST /cases/{case_id}/analyse    — 发起分析
POST /cases/{case_id}/risks/{risk_id}/review — 审核风险项
POST /cases/{case_id}/task-drafts   — 生成任务草稿
POST /cases/{case_id}/task-drafts/{draft_id}/simulated-publish — 模拟发布
POST /cases/{case_id}/tasks/{task_id}/supplement — 补充任务执行信息
POST /cases/{case_id}/close    — 关闭病例协同
POST /cases/{case_id}/cancel   — 取消病例协同
POST /cases/{case_id}/reconcile — 重新核实（知识变更后）
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.workflow.models import AuditEvent, Case, RiskItem, TaskDraft, get_session
from zhenhu.workflow.schemas import (
    AnalyseResponse,
    CaseCreate,
    CaseResponse,
    KnowledgeChangedHookRequest,
    KnowledgeChangedHookResponse,
    ReviewRequest,
    RiskItemResponse,
    SimulatedPublishResponse,
    SupplementRequest,
    SupplementResponse,
    TaskDraftResponse,
    UnifiedResponse,
)
from zhenhu.workflow.state_machine import CaseStateMachine, StateMachineError

router = APIRouter(prefix="/cases", tags=["cases"])

# ============================================================================
# 跨服务 URL 配置
# ============================================================================

KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8200")
FHIR_URL = os.environ.get("FHIR_URL", "http://localhost:8300")


# 依赖注入：获取当前 request_id
def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


# ============================================================================
# 分析关键词 → 风险类别映射
# ============================================================================

_KEYWORD_CATEGORY_MAP: dict[str, str] = {
    "药物": "medication_allergy",
    "过敏": "medication_allergy",
    "检验": "followup_window",
    "随访": "followup_window",
    "医嘱": "missing_field",
    "交接": "missing_field",
}


# 模拟分析引擎（阶段 0 占位，后续由 Agent 编排替代）
_MOCK_RISKS: list[dict] = [
    {
        "category": "medication_allergy",
        "severity": "high",
        "severity_label": "高风险",
        "title": "出院药物与已记录过敏史存在潜在冲突",
        "summary": "出院带药清单中出现阿莫西林/克拉维酸钾；输入快照记录青霉素类药物致皮疹。系统不作临床结论，请医生核实。",
        "evidence_snippet": "青霉素类（皮疹）",
        "citation_excerpt": "对青霉素类药物有过敏史者，应由具备处方责任的医师评估。",
        "citation_document_id": "drug-label-amoxicillin-clavulanate",
    },
    {
        "category": "followup_window",
        "severity": "medium",
        "severity_label": "中风险",
        "title": "肾功能结果与随访计划时间窗不一致",
        "summary": "最近肌酐采集时间为出院前 36 小时；随访草稿未包含复查时间。请核实是否需要补充院后监测安排。",
        "evidence_snippet": "肌酐采集时间：出院前 36 小时",
        "citation_excerpt": "复查事项和计划时间应在交接草稿中明确记录。",
        "citation_document_id": "zhenhu-handoff-sop",
    },
    {
        "category": "missing_field",
        "severity": "low",
        "severity_label": "低风险",
        "title": "居家血压自测记录字段未见填写",
        "summary": "交接单草稿未包含居家自测记录方式。该项仅提示信息完整性，不替代临床判断。",
        "evidence_snippet": "居家血压记录字段为空",
        "citation_excerpt": "交接信息应包含约定的居家监测记录方式。",
        "citation_document_id": "zhenhu-handoff-sop",
    },
]


async def _fetch_knowledge_for_keyword(
    client: httpx.AsyncClient, keyword: str
) -> tuple[str, dict | None]:
    """阶段 0: 通过知识编排服务获取检索结果（单次调用）。

    Args:
        client: 共享的 httpx 异步客户端。
        keyword: 检索关键词（如 "药物"、"过敏"、"检验"、"随访"）。

    Returns:
        tuple[str, dict | None]: (keyword, citation_dict)；
                     搜索失败或无结果时 citation_dict 为 None。
    """
    try:
        resp = await client.get(
            f"{KNOWLEDGE_URL}/knowledge/search",
            params={"q": keyword},
        )
        if resp.status_code == 200:
            body = resp.json()
            results = body.get("data", {}).get("results", [])
            if results:
                first = results[0]
                return keyword, {
                    "citation_excerpt": (
                        first.get("citation", {}).get("excerpt", "")
                        or (first.get("text", "") or "")[:200]
                    )[:200],
                    "citation_document_id": first.get("document_id", ""),
                    "evidence_snippet": (
                        first.get("citation", {}).get("excerpt", "")
                        or (first.get("text", "") or "")[:100]
                    )[:100],
                }
    except Exception:
        # 搜索失败时保留原有 mock evidence，不阻断分析流程
        pass
    return keyword, None


async def _analyse_and_generate_risks(
    session: AsyncSession, sm: CaseStateMachine, case: Case
) -> list[RiskItem]:
    """阶段 0: 通过知识编排服务获取检索结果，生成风险项并写入数据库。

    并发对每个内置关键词调 knowledge-orchestrator 搜索。
    搜索成功时用返回的 citation 信息填充风险项的 evidence；
    搜索失败时保留原有 mock evidence，不阻断分析流程。
    """
    # ---- 阶段 0: 通过知识编排服务获取检索结果 ----
    keywords = ["药物", "过敏", "检验", "随访"]
    kw_citations: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=2.0) as client:
        tasks = [_fetch_knowledge_for_keyword(client, kw) for kw in keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                kw, cit = result
                if cit is not None:
                    kw_citations[kw] = cit

    # 按类别聚合：同一类别的多个关键词取第一个命中的结果
    category_citation: dict[str, dict] = {}
    for kw, cit in kw_citations.items():
        cat = _KEYWORD_CATEGORY_MAP.get(kw)
        if cat and cat not in category_citation:
            category_citation[cat] = cit

    # ---- 生成风险项 ----
    risks: list[RiskItem] = []
    for mock_risk in _MOCK_RISKS:
        cat = mock_risk["category"]
        # 搜索成功时用真实 citation 填充 evidence；搜索失败时保留 mock evidence
        if cat in category_citation:
            cit = category_citation[cat]
            evidence_snippet = cit["evidence_snippet"]
            citation_excerpt = cit["citation_excerpt"]
            citation_document_id = cit["citation_document_id"]
        else:
            evidence_snippet = mock_risk["evidence_snippet"]
            citation_excerpt = mock_risk["citation_excerpt"]
            citation_document_id = mock_risk["citation_document_id"]

        risk = RiskItem(
            case_id=case.case_id,
            category=mock_risk["category"],
            severity=mock_risk["severity"],
            severity_label=mock_risk["severity_label"],
            title=mock_risk["title"],
            summary=mock_risk["summary"],
            status="pending",
            evidence_snippet=evidence_snippet,
            citation_excerpt=citation_excerpt,
            citation_document_id=citation_document_id,
        )
        session.add(risk)
        risks.append(risk)
    await session.flush()
    return risks


async def _fetch_patient_from_fhir(patient_id: str) -> str | None:
    """阶段 0: 通过 FHIR 适配层获取患者数据。

    调用 GET {FHIR_URL}/fhir/Patient/{patient_id} 获取患者姓名引用。
    成功时返回脱敏后的患者姓名；失败时返回 None。

    Args:
        patient_id: FHIR 患者 ID（以 pat- 开头）。

    Returns:
        str | None: 患者姓名 token（脱敏），失败时返回 None。
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{FHIR_URL}/fhir/Patient/{patient_id}")
            if resp.status_code == 200:
                body = resp.json()
                data = body.get("data")
                if data:
                    name_list = data.get("name", [])
                    if name_list:
                        return name_list[0].get("text", None)
    except Exception:
        pass
    return None


# ============================================================================
# 端点
# ============================================================================


@router.post("", status_code=201)
async def create_case(
    body: CaseCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """创建新病例。

    初始状态为 draft，随后可由经治医生发起分析。
    """
    request_id = get_request_id(request)

    # ---- 阶段 0: 通过 FHIR 适配层获取患者数据 ----
    patient_ref: str | None = None
    if body.input_snapshot_id and body.input_snapshot_id.startswith("pat-"):
        fhir_name = await _fetch_patient_from_fhir(body.input_snapshot_id)
        if fhir_name:
            patient_ref = fhir_name
        else:
            # 失败时用 snapshot_id 作为 fallback
            patient_ref = body.input_snapshot_id
    else:
        patient_ref = body.input_snapshot_id

    case = Case(
        input_snapshot_id=body.input_snapshot_id,
        patient_ref=patient_ref,
        state="draft",
        workflow_version="0.2.0",
    )
    session.add(case)
    await session.flush()
    await session.commit()

    resp = CaseResponse.model_validate(case)
    return UnifiedResponse(request_id=request_id, data=resp, error=None)


@router.get("/{case_id}")
async def get_case(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """查询病例概览。

    返回病例基本状态、风险项列表、任务草稿（若存在）和审计事件数量。
    case 不存在时返回 404。
    """
    request_id = get_request_id(request)

    # 1. 查 Case
    result = await session.execute(
        select(Case).where(Case.case_id == case_id)
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    # 2. 查 RiskItems
    risk_result = await session.execute(
        select(RiskItem).where(RiskItem.case_id == case_id)
    )
    risks = list(risk_result.scalars().all())

    # 3. 查 TaskDraft（若有）
    draft_result = await session.execute(
        select(TaskDraft).where(TaskDraft.case_id == case_id)
    )
    draft = draft_result.scalar_one_or_none()

    # 4. 统计 AuditEvents
    count_result = await session.execute(
        select(func.count(AuditEvent.id)).where(AuditEvent.case_id == case_id)
    )
    audit_event_count = count_result.scalar() or 0

    # 组装响应
    resp = CaseResponse(
        case_id=case.case_id,
        state=case.state,
        input_snapshot_id=case.input_snapshot_id,
        patient_ref=case.patient_ref,
        workflow_version=case.workflow_version,
        created_at=case.created_at,
        updated_at=case.updated_at,
        risks=[RiskItemResponse.model_validate(r) for r in risks],
        task_draft=TaskDraftResponse.model_validate(draft) if draft else None,
        audit_event_count=audit_event_count,
    )
    return UnifiedResponse(request_id=request_id, data=resp, error=None)


@router.post("/{case_id}/analyse")
async def analyse_case(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[AnalyseResponse]:
    """发起病例分析。

    状态转移：draft | failed | knowledge_changed → analysing → review_pending。
    分析过程生成风险项并保存到数据库。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        # 转移 → analysing
        await sm.transition(
            case=case,
            next_state="analysing",
            actor="doctor",
            event_type="analysis_started",
            title="启动分析",
            detail="执行数据质量规则、确定性规则和知识检索",
        )

        # 分析：生成风险项（阶段 0: 通过知识编排服务获取检索结果）
        risks = await _analyse_and_generate_risks(session, sm, case)

        # 转移 → review_pending
        await sm.transition(
            case=case,
            next_state="review_pending",
            actor="system",
            event_type="analysis_completed",
            title="分析完成，等待医生审核",
            detail=f"生成 {len(risks)} 项风险，待医生审核",
        )

        risk_responses = [RiskItemResponse.model_validate(r) for r in risks]
        await session.commit()

        data = AnalyseResponse(
            case_id=case.case_id,
            state=case.state,
            risk_items=risk_responses,
        )
        return UnifiedResponse(request_id=request_id, data=data, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc


@router.post("/{case_id}/risks/{risk_id}/review")
async def review_risk(
    case_id: str,
    risk_id: str,
    body: ReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """审核风险项。

    仅当病例状态为 review_pending 时可操作。
    所有风险项审核完毕后，自动转移至 confirmed（全部确认）或 rejected（存在驳回）。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    if case.state != "review_pending":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CASE_STATE_CONFLICT",
                "message": "当前状态不允许审核风险项",
                "details": {"current_state": case.state},
            },
        )

    # 查找风险项
    risks = await sm.get_risks_by_case_id(case_id)
    target_risk = next((r for r in risks if r.risk_id == risk_id), None)
    if target_risk is None:
        raise HTTPException(
            status_code=404, detail=f"Risk item not found: {risk_id}"
        )

    if target_risk.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CASE_STATE_CONFLICT",
                "message": "该风险项已完成审核",
                "details": {"current_risk_status": target_risk.status},
            },
        )

    # 更新风险项状态
    new_status = "confirmed" if body.action in ("confirm",) else "rejected"
    await sm.update_risk_status(
        risk=target_risk,
        status=new_status,
        decision=body.action,
        note=body.note,
    )

    # 检查是否所有风险项都已审核完毕
    if await sm.all_risks_reviewed(case_id):
        any_rejected = await sm.any_risk_rejected(case_id)
        next_state = "rejected" if any_rejected else "confirmed"
        title = (
            "全部风险项已审核，存在驳回项" if any_rejected else "全部风险项已确认"
        )
        try:
            await sm.transition(
                case=case,
                next_state=next_state,
                actor="doctor",
                event_type="review_resolved",
                title=title,
                detail=f"病例进入 {next_state} 状态",
            )
        except StateMachineError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                },
            ) from exc

    await session.commit()
    resp = CaseResponse.model_validate(case)
    return UnifiedResponse(request_id=request_id, data=resp, error=None)


# ============================================================================
# 新增端点（完整协同链路）
# ============================================================================


@router.post("/{case_id}/task-drafts")
async def create_task_draft(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[TaskDraftResponse]:
    """生成任务草稿。

    仅在 confirmed 或 rejected 状态下允许。
    收集所有已确认风险项，生成 3 条模拟协同任务。
    状态转移：confirmed | rejected → task_draft。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        result = await sm.create_task_draft(case=case, actor="doctor")

        await session.commit()

        # 构造响应（TaskDraftResponse 需要 TaskDraft ORM 对象）
        draft = await sm.get_task_draft_by_id(result["draft_id"])
        resp = TaskDraftResponse.model_validate(draft)
        return UnifiedResponse(request_id=request_id, data=resp, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc


@router.post("/{case_id}/task-drafts/{draft_id}/simulated-publish")
async def simulated_publish(
    case_id: str,
    draft_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[SimulatedPublishResponse]:
    """模拟发布任务草稿。

    仅在 task_draft 状态下允许。
    先检查是否 knowledge_changed 阻断，再发布。
    状态转移：task_draft → simulated_published。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        result = await sm.publish_simulated(
            case=case, draft_id=draft_id, actor="doctor"
        )

        await session.commit()

        data = SimulatedPublishResponse(state=result["state"])
        return UnifiedResponse(request_id=request_id, data=data, error=None)

    except StateMachineError as exc:
        status_code = 409
        detail = {
            "code": exc.code,
            "message": str(exc),
            "details": exc.details,
        }
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/{case_id}/tasks/{task_id}/supplement")
async def supplement_task(
    case_id: str,
    task_id: str,
    body: SupplementRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[SupplementResponse]:
    """补充任务执行信息。

    仅在 task_draft 或 simulated_published 状态下允许。
    需要操作人角色与任务指派的 assignee_role 匹配。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    # 从 header 读取角色（默认 nurse 方便测试）
    actor = request.headers.get("X-User-Role", "nurse")

    try:
        result = await sm.supplement_task(
            case=case,
            task_id=task_id,
            actor=actor,
            result=body.result,
            note=body.note,
        )

        await session.commit()

        data = SupplementResponse(
            task_id=result["task_id"],
            status=result["status"],
            execution_result=result["execution_result"],
            execution_note=result["execution_note"],
        )
        return UnifiedResponse(request_id=request_id, data=data, error=None)

    except StateMachineError as exc:
        status_code = 403 if exc.code == "FORBIDDEN" else 409
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc


@router.post("/{case_id}/close")
async def close_case(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """关闭病例协同。

    仅在 simulated_published 状态下允许。
    状态转移：simulated_published → closed。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        await sm.close_case(case=case, actor="doctor")

        await session.commit()

        resp = CaseResponse.model_validate(case)
        return UnifiedResponse(request_id=request_id, data=resp, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc


@router.post("/{case_id}/cancel")
async def cancel_case(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """取消病例协同。

    任意非终态（!closed && !cancelled）下允许。
    状态转移：当前状态 → cancelled。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        await sm.cancel_case(case=case, actor="doctor")

        await session.commit()

        resp = CaseResponse.model_validate(case)
        return UnifiedResponse(request_id=request_id, data=resp, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc


@router.post("/{case_id}/reconcile")
async def reconcile_case(
    case_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[CaseResponse]:
    """重新核实（知识变更后重新分析）。

    仅在 knowledge_changed 状态下允许。
    清除旧风险项，重新执行分析生成新风险项。
    状态转移：knowledge_changed → review_pending。
    """
    request_id = get_request_id(request)
    sm = CaseStateMachine(session)

    case = await sm.get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        # 1. 删除旧风险项
        old_risks = await sm.get_risks_by_case_id(case_id)
        for risk in old_risks:
            await session.delete(risk)
        await session.flush()

        # 2. 重新执行分析：生成新风险项（阶段 0: 通过知识编排服务获取检索结果）
        new_risks = await _analyse_and_generate_risks(session, sm, case)

        # 3. 状态转移：knowledge_changed → review_pending
        await sm.reconcile_case(case=case, actor="doctor")

        await session.commit()

        resp = CaseResponse.model_validate(case)
        return UnifiedResponse(request_id=request_id, data=resp, error=None)

    except StateMachineError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc
