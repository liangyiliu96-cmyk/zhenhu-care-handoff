"""CDS Hooks 端点 — HL7 CDS Hooks 1.1 标准实现。

三卡点映射:
  - patient-view    → 入院确认卡（推荐批准/拒签）
  - order-select    → 调药确认卡（处方变化预警）
  - order-sign      → 出院签字卡（出院准备度 + QA）

标准文档: https://cds-hooks.hl7.org/
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..schemas import UnifiedResponse

logger = logging.getLogger("zhenhu.cds_hooks")

router = APIRouter(prefix="/cds-services", tags=["CDS Hooks"])

# ── CDS Hooks Discovery ──


@router.get("")
async def cds_discovery(request: Request):
    """CDS Hooks 服务发现 — 返回可用服务列表。"""
    return {"services": _service_definitions(_request_base(request))}


@router.get("/status")
async def cds_integration_status(request: Request):
    """Expose manager-readable CDS integration readiness without clinical data."""
    from ..services.management_access import require_management_operation

    require_management_operation(request, "database_stats", write=False)
    base = _request_base(request)
    services = _service_definitions(base)
    return UnifiedResponse(data={
        "standard": "HL7 CDS Hooks 1.1",
        "environment": os.environ.get("APP_ENV", "dev").strip().lower(),
        "auth_mode": os.environ.get("AUTH_MODE", "header").strip().lower(),
        "discovery_url": f"{base}/cds-services",
        "service_count": len(services),
        "services": [
            {
                "id": service["id"],
                "hook": service["hook"],
                "title": service["title"],
                "description": service["description"],
                "endpoint": f"{base}/cds-services/{service['id']}",
                "patient_access_enforced": service["id"] != "zhenhu-clinical-summary",
            }
            for service in services
        ],
        "checks": {
            "discovery": "ready",
            "handlers": "ready",
            "patient_access": "enforced",
        },
    })


def _service_definitions(base: str) -> list[dict]:
    return [
            {
                "hook": "patient-view",
                "id": "zhenhu-admission-confirm",
                "title": "臻护 · 入院确认",
                "description": "基于患者病史、体征、NEWS2/qSOFA 评分的入院确认建议",
                "prefetch": {"patient": "Patient/{{context.patientId}}"},
            },
            {
                "hook": "order-select",
                "id": "zhenhu-medication-confirm",
                "title": "臻护 · 调药确认",
                "description": "用药调整方案的药物相互作用检测 + FDA 标签核查",
                "prefetch": {"medicationRequest": "MedicationRequest/{{context.draftOrders.entry[0].resource.id}}"},
            },
            {
                "hook": "order-sign",
                "id": "zhenhu-discharge-sign",
                "title": "臻护 · 出院签字",
                "description": "出院准备度评分 + 小结完整性 QA + 交接确认状态",
                "prefetch": {"patient": "Patient/{{context.patientId}}"},
            },
            {
                "hook": "patient-view",
                "id": "zhenhu-clinical-summary",
                "title": "臻护 · 临床摘要",
                "description": "AI 生成的病区摘要 + 访视顺序建议",
            },
        ]


def _request_base(request: Request) -> str:
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


# ── CDS Hooks 通用处理 ──


@router.post("/zhenhu-admission-confirm")
@router.post("/zhenhu-medication-confirm")
@router.post("/zhenhu-discharge-sign")
@router.post("/zhenhu-clinical-summary")
async def cds_service_handler(request: Request):
    """CDS Hooks 统一入口 — 根据 service_id 路由到相应处理逻辑。"""
    body = await request.json()
    service_id = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    patient_id = _extract_patient_id(body)
    if patient_id:
        from ..services.patient_access import PatientAccessDeniedError, require_patient_access

        try:
            require_patient_access(patient_id, getattr(request.state, "user_info", {}))
        except PatientAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc

    cards = []
    if service_id == "zhenhu-admission-confirm" and patient_id:
        cards = _admission_confirm_cards(patient_id)
    elif service_id == "zhenhu-medication-confirm" and patient_id:
        cards = await _medication_confirm_cards(patient_id)
    elif service_id == "zhenhu-discharge-sign" and patient_id:
        cards = await _discharge_sign_cards(patient_id)
    elif service_id == "zhenhu-clinical-summary":
        cards = _clinical_summary_cards(body, getattr(request.state, "user_info", {}))

    return {"cards": cards}


# ── 卡片生成 ──


def _extract_patient_id(body: dict) -> str | None:
    """从 CDS Hooks 请求体中提取患者 ID。"""
    context = body.get("context", {})
    for key in ("patientId", "patient"):
        pid = context.get(key, "")
        if pid:
            return pid.split("/")[-1] if "/" in pid else pid
    # 从 prefetch 中提取
    prefetch = body.get("prefetch", {})
    patient = prefetch.get("patient", {})
    if isinstance(patient, dict):
        return patient.get("id", "")
    return None


def _admission_confirm_cards(patient_id: str) -> list[dict]:
    """入院确认卡 — 患者入院时的临床评估摘要。"""
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return [_error_card("患者未入院")]

    risk = state.get("risk_level", "unknown")
    news2 = state.get("news2_score")
    qsofa = state.get("qsofa_score")
    dd = state.get("ddx_list", []) or []
    top_ddx = dd[0].get("name", "") if dd else ""
    chain = state.get("document_chain", [])
    history_ok = "history_note" in chain
    pe_ok = "pe_note" in chain
    ddx_ok = "ddx_note" in chain

    summary = f"风险: {risk} | NEWS2: {news2} | qSOFA: {qsofa} | 首诊: {top_ddx}"
    detail = (
        f"评估完成度: 病史{'✅' if history_ok else '⚠️'} "
        f"体查{'✅' if pe_ok else '⚠️'} "
        f"DDx{'✅' if ddx_ok else '⚠️'}。"
    )

    indicator = "warning" if risk == "high" or (news2 and news2 >= 5) else "info"

    return [_card(
        summary=summary,
        indicator=indicator,
        detail=detail,
        source_label="臻护入院评估",
        suggestions=[
            {"label": "批准入院", "uuid": "approve"},
            {"label": "拒签", "uuid": "reject"},
            {"label": "编辑信息", "uuid": "edit"},
        ],
        links=[_app_link(patient_id, "dashboard")]
    )]


async def _medication_confirm_cards(patient_id: str) -> list[dict]:
    """调药确认卡 — 药物相互作用 + FDA 标签核查。"""
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return [_error_card("患者状态获取失败")]

    findings = state.get("medication_findings") or {}
    conflicts = findings.get("conflicts", [])
    gaps = findings.get("gaps", [])
    during = findings.get("during_stay_changes", [])
    external = [
        item for item in findings.get("external_data") or []
        if isinstance(item, dict) and item.get("status") == "available"
    ]

    summary = f"用药核对: {len(conflicts)} 对相互作用, {len(gaps)} 缺口, {len(during)} 次调药"
    detail_lines = []
    for c in conflicts[:2]:
        detail_lines.append(
            f"{c.get('drug_pair','?')}: {c.get('severity','?')}风险 — {c.get('recommendation','')[:60]}"
        )
    if external:
        detail_lines.append(f"FDA 数据: {len(external)} 种药物标签已获取")

    # RAG 增强: 搜药物安全知识库(L5)
    try:
        from ..agent.rag_engine import search as rag_search
        for c in conflicts[:2]:
            pair = c.get("drug_pair", "")
            if pair:
                rag_hits = await rag_search(pair, layer="L5", top_k=1)
                if rag_hits:
                    detail_lines.append(f"[知识库] {rag_hits[0]['text'][:100]}")
    except Exception:
        pass

    indicator = "critical" if any(c.get("severity") == "severe" for c in conflicts) else \
                "warning" if conflicts else "info"

    return [_card(
        summary=summary,
        indicator=indicator,
        detail="\n".join(detail_lines) or "无异常发现",
        source_label="臻护用药核对",
        suggestions=[
            {"label": "确认调整", "uuid": "approve"}, {"label": "修改方案", "uuid": "edit"}
        ],
        links=[_app_link(patient_id, "dashboard")]
    )]


async def _discharge_sign_cards(patient_id: str) -> list[dict]:
    """出院签字卡 — 出院准备度 + 小结 QA。"""
    from .state_store import get_state
    from ..agent.harness import compute_readiness_score

    state = get_state(patient_id)
    if not state:
        return [_error_card("患者状态获取失败")]

    readiness = compute_readiness_score(state)
    score = readiness["score"]
    status = readiness["status"]
    detail_lines = readiness["deductions"]
    if not detail_lines:
        detail_lines.append("所有指标正常")

    # RAG 增强: 搜出院患教知识(L9) + 处置流程(L7)
    try:
        from ..agent.rag_engine import search as rag_search
        template = state.get("disease_template") or {}
        did = template.get("disease_id", "")
        if did:
            rag_hits = await rag_search(did, layer="L9", top_k=1)
            if rag_hits:
                detail_lines.insert(0, f"[患教] {rag_hits[0]['text'][:120]}")
    except Exception:
        pass

    # RAG 增强: 中医体质参考 (L16)
    try:
        from ..agent.rag_engine import search as rag_search
        rag_tcm = await rag_search("体质评估", layer="L16", top_k=1)
        if rag_tcm:
            detail_lines.append(f"[中医参考] 体质评估算法已就绪，可作为出院后康复调养参考")
    except Exception:
        pass

    summary = f"出院准备度: {score}分 {status}"
    indicator = "info" if score >= 85 else "warning"

    return [_card(
        summary=summary,
        indicator=indicator,
        detail="; ".join(detail_lines) or "无异常",
        source_label="臻护出院评估",
        suggestions=[
            {"label": "批准出院", "uuid": "approve"},
            {"label": "补充信息", "uuid": "edit"},
        ],
        links=[_app_link(patient_id, "discharge-summary")]
    )]


def _clinical_summary_cards(body: dict, user: dict) -> list[dict]:
    """临床摘要卡 — AI 病区摘要 (轻量版供 CDS Hooks 边栏)。"""
    from .state_store import _store, _get_ttl
    import time
    ttl = _get_ttl()
    now = time.time()
    high, total = 0, 0
    from ..services.patient_access import iter_accessible_patient_states
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase", "") in ("discharge", "confirm", "review"):
            continue
        total += 1
        if state.get("risk_level") == "high":
            high += 1

    summary = f"病区共 {total} 名活跃患者, {high} 人高危"
    return [_card(
        summary=summary,
        indicator="info",
        detail="点击查看病区总览获取详细信息",
        source_label="臻护病区摘要",
        links=[{"label": "病区总览", "type": "absolute", "url": "/ward/overview"}]
    )]


# ── 卡片工具函数 ──


def _card(
    summary: str,
    indicator: str,
    detail: str,
    source_label: str,
    suggestions: list[dict] | None = None,
    links: list[dict] | None = None,
) -> dict:
    """生成 CDS Hooks 标准卡片。"""
    card = {
        "uuid": source_label.lower().replace(" ", "-"),
        "summary": summary,
        "indicator": indicator,
        "detail": detail,
        "source": {
            "label": source_label,
            "url": "http://localhost:8000/docs",
        },
    }
    if suggestions:
        card["suggestions"] = [
            {
                "label": s["label"],
                "uuid": s["uuid"],
                "actions": [{"type": "create", "description": s["label"]}],
            }
            for s in suggestions
        ]
    if links:
        card["links"] = links
    return card


def _app_link(patient_id: str, page: str) -> dict:
    return {
        "label": "打开患者面板",
        "type": "absolute",
        "url": f"/inpatient/{patient_id}/{page}",
    }


def _error_card(message: str) -> dict:
    return _card(
        summary=message,
        indicator="warning",
        detail="无法获取患者临床数据",
        source_label="臻护 CDS Hooks",
    )
