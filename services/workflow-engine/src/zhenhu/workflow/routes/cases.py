"""病例相关 API 端点。

POST /cases                 — 创建病例
POST /cases/{case_id}/analyse    — 发起分析
POST /cases/{case_id}/risks/{risk_id}/review — 审核风险项
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.workflow.models import Case, RiskItem, get_session, _utcnow
from zhenhu.workflow.schemas import (
    AnalyseResponse,
    CaseCreate,
    CaseResponse,
    RiskItemResponse,
    ReviewRequest,
    UnifiedResponse,
)
from zhenhu.workflow.state_machine import CaseStateMachine, StateMachineError

router = APIRouter(prefix="/cases", tags=["cases"])


# 依赖注入：获取当前 request_id
def get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


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
        "citation_document_id": "poc-followup-sop",
    },
    {
        "category": "missing_field",
        "severity": "low",
        "severity_label": "低风险",
        "title": "居家血压自测记录字段未见填写",
        "summary": "交接单草稿未包含居家自测记录方式。该项仅提示信息完整性，不替代临床判断。",
        "evidence_snippet": "居家血压记录字段为空",
        "citation_excerpt": "交接信息应包含约定的居家监测记录方式。",
        "citation_document_id": "poc-followup-sop",
    },
]


async def _analyse_and_generate_risks(
    session: AsyncSession, sm: CaseStateMachine, case: Case
) -> list[RiskItem]:
    """模拟分析：生成风险项并写入数据库。"""
    risks: list[RiskItem] = []
    for mock_risk in _MOCK_RISKS:
        risk = RiskItem(
            case_id=case.case_id,
            category=mock_risk["category"],
            severity=mock_risk["severity"],
            severity_label=mock_risk["severity_label"],
            title=mock_risk["title"],
            summary=mock_risk["summary"],
            status="pending",
            evidence_snippet=mock_risk["evidence_snippet"],
            citation_excerpt=mock_risk["citation_excerpt"],
            citation_document_id=mock_risk["citation_document_id"],
        )
        session.add(risk)
        risks.append(risk)
    await session.flush()
    return risks


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

    case = Case(
        input_snapshot_id=body.input_snapshot_id,
        state="draft",
        workflow_version="0.2.0",
    )
    session.add(case)
    await session.flush()
    await session.commit()

    resp = CaseResponse.model_validate(case)
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

        # 模拟分析：生成风险项
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
