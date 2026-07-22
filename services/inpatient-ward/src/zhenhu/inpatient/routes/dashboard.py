"""医生 Dashboard 端点 — 主动查看患者全貌面板。

GET /inpatient/{patient_id}/dashboard
纯 state_store 读取，不经过 graph，零副作用。
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from ..schemas import UnifiedResponse
from ..services.clinical_alerts import alert_message
from ..services.clinical_brief import build_clinical_brief
from .route_schemas import DashboardResponse, VitalTrendItem, AbnormalLabItem
from ..agent.harness import compute_readiness_score

router = APIRouter(prefix="/inpatient", tags=["dashboard"])


def _require_patient_read_access(request: Request, patient_id: str) -> None:
    from ..services.patient_access import PatientAccessDeniedError, require_patient_access

    try:
        require_patient_access(patient_id, getattr(request.state, "user_info", {}))
    except PatientAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="无权访问该患者记录") from exc


def _calc_vital_trend(vital_signs: list[dict]) -> list[VitalTrendItem]:
    """从体征序列取最近 6 次，计算趋势方向。"""
    recent = (vital_signs or [])[-6:]
    items = []
    for vs in recent:
        items.append(VitalTrendItem(
            timestamp=vs.get("timestamp", ""),
            heart_rate=vs.get("heart_rate"),
            blood_pressure=vs.get("blood_pressure") or (
                f"{vs.get('systolic','')}/{vs.get('diastolic','')}"
                if vs.get("systolic") else None
            ),
            spo2=vs.get("spo2"),
            temperature=vs.get("temperature"),
        ))
    return items


def _calc_trend_direction(vital_signs: list[dict]) -> dict:
    """计算各体征的趋势方向: up | down | stable | unknown。"""
    recent = (vital_signs or [])[-6:]
    if len(recent) < 2:
        return {"heart_rate": "unknown", "blood_pressure": "unknown",
                "spo2": "unknown", "temperature": "unknown"}

    result = {}
    for key, field in [("heart_rate", "heart_rate"), ("spo2", "spo2"),
                        ("temperature", "temperature")]:
        first = recent[0].get(field)
        last = recent[-1].get(field)
        if first is None or last is None:
            result[key] = "unknown"
        elif last > first * 1.05:
            result[key] = "up"
        elif last < first * 0.95:
            result[key] = "down"
        else:
            result[key] = "stable"

    # 血压用 systolic
    first_sys = recent[0].get("systolic_mmhg") or recent[0].get("systolic")
    last_sys = recent[-1].get("systolic_mmhg") or recent[-1].get("systolic")
    if first_sys is None or last_sys is None:
        result["blood_pressure"] = "unknown"
    elif last_sys > first_sys * 1.05:
        result["blood_pressure"] = "up"
    elif last_sys < first_sys * 0.95:
        result["blood_pressure"] = "down"
    else:
        result["blood_pressure"] = "stable"

    return result


def _get_abnormal_labs(state: dict) -> list[AbnormalLabItem]:
    """从 lab_results 和模板参考范围筛选异常。"""
    labs = state.get("lab_results", []) or []
    template = state.get("disease_template", {}) or {}
    lab_refs = template.get("lab_reference", {}) or {}

    abnormal = []
    for lab in labs:
        name = lab.get("name", "")
        value = lab.get("value")
        unit = lab.get("unit", "")
        ref = lab_refs.get(name, {})
        ref_range = f"{ref.get('low','')}-{ref.get('high','')}" if ref else None

        if ref and value is not None:
            low = ref.get("low")
            high = ref.get("high")
            try:
                val = float(value)
                if (low is not None and val < low) or (high is not None and val > high):
                    abnormal.append(AbnormalLabItem(
                        name=name, value=str(value), unit=unit, ref_range=ref_range))
            except (ValueError, TypeError):
                pass
    return abnormal


def _compute_delta(vs: list, alerts: list, state: dict) -> dict:
    """计算本轮 vs 上一轮的变化摘要。"""
    if len(vs) < 2:
        return {"summary": "首轮监测，无可对比数据"}
    latest, prev = vs[-1], vs[-2]
    changes = []
    for key, label, unit in [
        ("systolic_mmhg", "收缩压", "mmHg"), ("diastolic_mmhg", "舒张压", "mmHg"),
        ("heart_rate", "心率", "bpm"), ("spo2", "SpO2", "%"),
        ("temperature", "体温", "℃"), ("respiratory_rate", "呼吸", "/min"),
    ]:
        cur = latest.get(key)
        pre = prev.get(key)
        if cur is not None and pre is not None:
            try:
                diff = round(float(cur) - float(pre), 1)
                if abs(diff) > 0:
                    direction = "↑" if diff > 0 else "↓"
                    changes.append(f"{label} {direction}{abs(diff)}{unit}")
            except (ValueError, TypeError):
                pass

    # 新增告警
    prev_alerts = len([a for a in alerts[:-3] if isinstance(a, str)])
    new_alert_count = max(0, len(alerts) - prev_alerts)

    return {
        "summary": "; ".join(changes) if changes else "体征无明显变化",
        "detail": changes,
        "new_alerts": new_alert_count,
        "total_rounds": state.get("round_count", 0),
    }


def _compute_med_journey(adjustments: list) -> list[dict]:
    """用药历程: 按时间线展示药物变更。"""
    journey = []
    for adj in (adjustments or [])[-8:]:
        drug = adj.get("drug") or adj.get("medication") or "未知"
        action = adj.get("action") or adj.get("type") or "用药"
        reason = adj.get("reason") or adj.get("dose") or ""
        source = adj.get("source", "ai")
        journey.append({
            "drug": str(drug)[:40],
            "action": str(action),
            "detail": str(reason)[:60],
            "source": "医生" if source == "doctor" else "AI建议",
        })
    return journey


def _medication_safety(state: dict) -> dict:
    """Project persisted medication reconciliation results without recomputing clinical rules on read."""
    findings = state.get("medication_findings") or {}
    completed = bool(findings) or "medication_reconciliation" in (state.get("document_chain") or [])

    conflicts = []
    for item in findings.get("conflicts") or []:
        if not isinstance(item, dict):
            continue
        evidence = str(item.get("evidence") or "")
        model_suggested = evidence.upper() == "LLM"
        conflicts.append({
            "drug_pair": str(item.get("drug_pair") or "未命名药物组合"),
            "severity": str(item.get("severity") or "moderate"),
            "mechanism": str(item.get("mechanism") or ""),
            "consequence": str(item.get("consequence") or ""),
            "recommendation": str(item.get("recommendation") or ""),
            "evidence": evidence,
            "source": str(item.get("source") or ("模型补充，需临床复核" if model_suggested else "规则库")),
            "model_suggested": model_suggested,
        })

    allergies = []
    for item in findings.get("allergy_contraindications") or []:
        if isinstance(item, dict):
            allergies.append({
                "medication": str(item.get("medication") or "未命名药物"),
                "allergen": str(item.get("allergen") or "已记录过敏原"),
                "severity": str(item.get("severity") or "major"),
                "recommendation": str(item.get("recommendation") or ""),
            })

    return {
        "status": "complete" if completed else "not_run",
        "conflicts": conflicts,
        "allergy_contraindications": allergies,
        "gaps": [str(item) for item in findings.get("gaps") or [] if str(item).strip()],
        "duplications": [str(item) for item in findings.get("duplications") or [] if str(item).strip()],
        "warnings": [str(item) for item in findings.get("llm_warnings") or [] if str(item).strip()],
        "external_evidence": [
            {
                "drug": str(item.get("drug") or "")[:120],
                "rxnorm_id": str(item.get("rxnorm_id") or "")[:40],
                "standard_name": str(item.get("standard_name") or "")[:160],
                "warnings": str(item.get("warnings") or "")[:200],
                "contraindications": str(item.get("contraindications") or "")[:200],
                "interactions": str(item.get("interactions") or "")[:200],
                "source": str(item.get("source") or "OpenFDA/RxNorm"),
                "status": "available" if item.get("status") == "available" else "unavailable",
            }
            for item in findings.get("external_data") or []
            if isinstance(item, dict) and str(item.get("drug") or "").strip()
        ],
    }


def _compute_pain_gcs(vs: list, state: dict) -> dict:
    """疼痛评分 + GCS 趋势。"""
    pain_scores = [v.get("pain_score") for v in vs[-6:] if v.get("pain_score") is not None]
    gcs_scores = [v.get("gcs") for v in vs[-6:] if v.get("gcs") is not None]
    pain_trend = "—"
    if len(pain_scores) >= 2:
        if pain_scores[-1] < pain_scores[0]:
            pain_trend = "↓改善" if pain_scores[-1] < pain_scores[0] * 0.7 else "↓轻度缓解"
        elif pain_scores[-1] > pain_scores[0]:
            pain_trend = "↑加重"

    return {
        "pain_latest": pain_scores[-1] if pain_scores else None,
        "pain_trend": pain_trend,
        "pain_location": state.get("patient_data", {}).get("pain_location", ""),
        "gcs_latest": gcs_scores[-1] if gcs_scores else None,
        "gcs_trend": "稳定" if len(gcs_scores) >= 2 and gcs_scores[-1] == gcs_scores[0] else None,
    }


def _compute_action_history(state: dict) -> list[dict]:
    """医生操作历史: 审核决策 + 命令记录。"""
    history = []
    # 三卡点状态
    for status_key, label in [
        ("doctor_confirm_status", "入院确认"), ("med_confirm_status", "调药确认"),
        ("discharge_sign_status", "出院签字"),
    ]:
        status = state.get(status_key)
        if status in ("approved", "signed"):
            history.append({"action": label, "decision": "批准", "by": "医生"})
        elif status == "rejected":
            history.append({"action": label, "decision": "拒签", "by": "医生"})

    # 拒签历史
    rejects = state.get("discharge_reject_history") or []
    for r in rejects[-3:]:
        if isinstance(r, dict):
            history.append({
                "action": "出院拒签", "decision": r.get("reason", "")[:60], "by": "医生"
            })
    return history[-5:]  # 最近 5 条


async def _compute_checklist(state: dict) -> list[dict]:
    """临床决策清单: 规则和已持久化建议。

    每个条目: task/urgency/status/action(可点击操作)
    """
    tpl = state.get("disease_template") or {}
    vs = state.get("vital_signs", []) or []
    latest = vs[-1] if vs else {}
    items = []

    # ── 规则层: 体征/检验异常 ──
    if latest.get("spo2", 100) < 92:
        items.append({"task": "评估低氧血症原因", "urgency": "high", "status": "待做",
                      "action": "查血气分析"})
    if latest.get("heart_rate", 80) > 110:
        items.append({"task": "评估心动过速", "urgency": "high", "status": "待做",
                      "action": "心电图"})
    if latest.get("temperature", 37) > 38:
        items.append({"task": "排查感染原因", "urgency": "high", "status": "待做",
                      "action": "血培养+CRP+PCT"})

    news2 = state.get("news2_score")
    if news2 is not None and news2 >= 5:
        items.append({"task": f"NEWS2={news2}，需复查血气", "urgency": "high", "status": "待做" if news2 >= 7 else "待做",
                      "action": "血气分析"})

    # ── 规则层: 流程卡点 ──
    meds = state.get("medication_adjustments", []) or []
    if meds and state.get("med_confirm_status") != "approved":
        items.append({"task": "确认用药调整方案", "urgency": "medium", "status": "待做",
                      "action": "review"})

    dc_check = state.get("discharge_criteria_check") or {}
    if dc_check.get("all_met"):
        items.append({"task": "符合出院标准，可启动出院流程", "urgency": "medium", "status": "待做",
                      "action": "discharge"})

    history = state.get("history_data"); pe = state.get("pe_data") or state.get("pe_narrative")
    if not history:
        items.append({"task": "完善病史信息", "urgency": "low", "status": "待做"})
    if not pe:
        items.append({"task": "完成体格检查记录", "urgency": "low", "status": "待做"})

    # ── 已完成标记 ──
    chain = state.get("document_chain", [])
    if "daily_round_note" in chain:
        items.append({"task": "查房已完成", "urgency": "low", "status": "完成"})
    if state.get("doctor_confirm_status") == "approved":
        items.append({"task": "入院确认已批准", "urgency": "low", "status": "完成"})
    if state.get("discharge_sign_status") == "signed":
        items.append({"task": "出院签字完成", "urgency": "low", "status": "完成"})

    # Dashboard reads must remain bounded. Reuse the recommendation generated
    # during the clinical workflow instead of issuing a new LLM request here.
    recommendation = str(state.get("ai_recommendation") or "").strip()
    if recommendation:
        items.insert(0, {
            "task": recommendation[:100], "urgency": "medium", "status": "待做", "source": "AI",
        })

    if not items:
        items.append({"task": "当前无需紧急处理", "urgency": "low", "status": "完成"})

    return items[-8:]  # 最多 8 条



async def _enrich_ddx_icd10(ddx: list) -> list[dict]:
    """DDx 列表增加 ICD-10 编码。失败不阻断。"""
    if not ddx:
        return []
    try:
        from ..agent.clinical_external import icd10_search
    except ImportError:
        return []
    enriched = []
    for d in ddx[:3]:
        name = d.get("name") or d.get("diagnosis") or ""
        code = None
        if name:
            results = await icd10_search(name, max_results=1)
            if results:
                code = results[0]["code"]
        enriched.append({"diagnosis": name, "icd10_code": code})
    return enriched


@router.get("/{patient_id}/dashboard")
async def get_dashboard(patient_id: str, request: Request):
    """获取患者全貌面板。

    聚合计算（纯 state_store 读取，不经过 graph）：
    - vital_trend: 最近 6 次体征 + 趋势方向
    - soap_summary: 最新 SOAP 摘要
    - ddx_top3: TOP 3 鉴别诊断
    - abnormal_labs: 超出参考范围的检验
    - medication_current: 当前用药
    - complication_alerts: 并发症/护理预警
    - discharge_criteria_status: 出院标准达标情况
    """
    _require_patient_read_access(request, patient_id)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(
            error={"code": "NOT_FOUND", "message": f"未找到患者状态: {patient_id}"}
        )

    vital_signs = state.get("vital_signs", []) or []
    latest_round = state.get("latest_round", {}) or {}
    ddx_list = state.get("ddx_list", []) or []
    medication_adjustments = state.get("medication_adjustments", []) or []
    clinical_alerts = state.get("clinical_alerts", []) or []
    nursing_alerts = state.get("nursing_alerts", []) or []
    from ..services.agent_flow import active_pending_review

    pending_review = active_pending_review(state) or {}

    ddx_sorted = sorted(
        ddx_list,
        key=lambda d: {"high": 0, "moderate": 1, "low": 2}.get(
            d.get("likelihood", "low"), 3)
    )

    response = DashboardResponse(
        patient_id=patient_id,
        patient_name=(state.get("patient_data") or {}).get("name", patient_id),
        state_version=state.get("state_version", 0),
        is_on_hold=state.get("doctor_command") == "hold",
        phase=state.get("phase", "unknown"),
        template_name=(
            (state.get("disease_template") or {}).get("name") or
            (state.get("disease_template") or {}).get("disease_id") or ""
        ),
        template_id=(state.get("disease_template") or {}).get("disease_id") or "",
        vital_trend=_calc_vital_trend(vital_signs),
        vital_trend_direction=_calc_trend_direction(vital_signs),
        soap_summary=latest_round if latest_round else None,
        ddx_top3=ddx_sorted[:3],
        abnormal_labs=_get_abnormal_labs(state),
        medication_current=medication_adjustments,
        complication_alerts=list(dict.fromkeys(
            [alert_message(alert) for alert in clinical_alerts + nursing_alerts]
        )),
        discharge_criteria_status=state.get("discharge_criteria_check"),
        discharge_blockers=build_clinical_brief(state).get("discharge_blockers", []),
        nursing_summary={
            "nursing_records": (state.get("nursing_records") or [])[-3:],
            "nursing_status": state.get("nursing_status", ""),
        },
        last_updated=state.get("last_updated", ""),
        # 医生面板优化: 变化视角
        delta_summary=_compute_delta(vital_signs, clinical_alerts, state),
        medication_journey=_compute_med_journey(medication_adjustments),
        pain_gcs_trend=_compute_pain_gcs(vital_signs, state),
        action_history=_compute_action_history(state),
        ai_recommendation=state.get("ai_recommendation") or "",
        decision_checklist=await _compute_checklist(state),
        discharge_readiness=compute_readiness_score(state),
        icd10_codes=await _enrich_ddx_icd10(ddx_sorted[:3]),
        medication_safety=_medication_safety(state),
        pending_review_type=pending_review.get("type", ""),
        pending_review_id=pending_review.get("review_id", ""),
        discharge_sign_status=state.get("discharge_sign_status") or "",
        handoff_acknowledged=bool(state.get("handoff_acknowledged")),
        patient_confirmation_status=state.get("patient_confirmation_status") or "",
        patient_confirmation_requirements=state.get("patient_confirmation_requirements") or [],
        patient_confirmation_evidence=state.get("patient_confirmation_evidence") or [],
        bridge_status=(state.get("bridge_result") or {}).get("status", ""),
        bridge_error=state.get("bridge_error") or "",
    )

    return UnifiedResponse(data=response.model_dump())


# ═══════════════════════════════════════════════════════════
# 方案4: 异常事件时间线
# ═══════════════════════════════════════════════════════════

from fastapi import APIRouter as _APIRouter

timeline_router = _APIRouter(prefix="/inpatient", tags=["timeline"])


@timeline_router.get("/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str, request: Request):
    """患者住院事件时间线 — 按 document_chain 顺序展示关键节点。

    每个文档映射到临床事件卡片(标识/时间/摘要)。
    纯 state_store 读，零副作用。
    """
    _require_patient_read_access(request, patient_id)
    from .state_store import get_state

    state = get_state(patient_id)
    if not state:
        return UnifiedResponse(error={"code": "NOT_FOUND", "message": f"未找到患者: {patient_id}"})

    chain = state.get("document_chain", [])

    # 事件映射: document_chain key → 临床事件名 + 图标
    EVENT_MAP = {
        "intake_note": {"label": "入院采集", "icon": "📋", "order": 1},
        "history_note": {"label": "病史采集", "icon": "📝", "order": 2},
        "pe_note": {"label": "体格检查", "icon": "🩺", "order": 3},
        "ddx_note": {"label": "鉴别诊断", "icon": "🧠", "order": 4},
        "medication_reconciliation": {"label": "用药核对", "icon": "💊", "order": 5},
        "risk_assessment": {"label": "风险分层", "icon": "⚠️", "order": 6},
        "doctor_confirm_auto": {"label": "入院确认", "icon": "✅", "order": 7},
        "padua_scored": {"label": "Padua VTE", "icon": "🩸", "order": 8},
        "vte_check": {"label": "VTE预防", "icon": "🛡️", "order": 9},
        "daily_round_note": {"label": "查房笔记", "icon": "🔍", "order": 10},
        "nursing_note": {"label": "护理记录", "icon": "👩‍⚕️", "order": 11},
        "shift_summary": {"label": "交班摘要", "icon": "📋", "order": 12},
        "lab_review": {"label": "检验审阅", "icon": "🧪", "order": 13},
        "news2_alert": {"label": "NEWS2告警", "icon": "🔔", "order": 14},
        "stroke_at_check": {"label": "卒中抗栓", "icon": "🧠", "order": 15},
        "discharge_signed": {"label": "出院签字", "icon": "✍️", "order": 16},
        "handoff_note": {"label": "交接事项", "icon": "🤝", "order": 17},
        "review_note": {"label": "医生审核", "icon": "👨‍⚕️", "order": 18},
        "discharge_bridge": {"label": "出院协同已创建", "icon": "🔗", "order": 18.5},
        "discharge_bridge_failed": {"label": "出院协同创建失败", "icon": "⚠️", "order": 18.6},
        "confirm_note": {"label": "确认出院", "icon": "🏠", "order": 19},
    }

    events = []
    for doc in chain:
        evt = EVENT_MAP.get(doc, {"label": doc.replace("_", " ").title(), "icon": "•", "order": 99})
        events.append({
            "key": doc,
            "label": evt["label"],
            "icon": evt["icon"],
            "order": evt["order"],
        })
    events.sort(key=lambda e: e["order"])

    # 伴随事件数据
    return UnifiedResponse(data={
        "patient_id": patient_id,
        "phase": state.get("phase"),
        "round_count": state.get("round_count", 0),
        "events": events,
        "alerts": (state.get("clinical_alerts") or [])[-5:],
        "ai_recommendation": state.get("ai_recommendation") or "",
    })
