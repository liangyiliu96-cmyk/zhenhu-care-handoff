"""病区优先级排序 — GET /ward/priority。

默认使用确定性临床规则返回最需关注的 3 人；可选 LLM 仅在
``?explain=true`` 时提供自然语言说明，不经过 graph。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request

from ..schemas import UnifiedResponse
from ..services.clinical_alerts import canonicalize_alert, canonicalize_alerts

router = APIRouter(prefix="/ward", tags=["ward"])


@router.get("/priority")
async def get_ward_priority(
    request: Request,
    explain: bool = Query(False, description="是否生成 LLM 优先级说明"),
):
    """返回最需关注的 TOP 3 患者，可选生成 LLM 排序说明。"""
    from .state_store import _store, _get_ttl

    ttl = _get_ttl()
    now = time.time()

    # 收集所有活跃患者摘要
    summaries = []
    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue
        p_data = state.get("patient_data", {}) or {}
        tpl = state.get("disease_template", {}) or {}
        vs = state.get("vital_signs", []) or []
        latest = vs[-1] if vs else {}
        alerts = state.get("clinical_alerts", []) or []

        summaries.append({
            "patient_id": pid,
            "name": p_data.get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "?"),
            "risk": state.get("risk_level"),
            "news2": state.get("news2_score"),
            "padua": state.get("padua_score"),
            "alerts": len(alerts),
            "round": state.get("round_count", 0),
            "bp": latest.get("systolic_mmhg"),
            "spo2": latest.get("spo2"),
            "discharge": state.get("discharge_decision", ""),
        })

    if not summaries:
        return UnifiedResponse(data={"total": 0, "top_patients": [], "reasoning": "病区无活跃患者"})

    # 默认走可解释的确定性排序，避免病区看板被可选 LLM 调用阻塞。
    # LLM 只为显式请求生成自然语言归并说明，不能影响临床规则排序。
    def _priority_score(patient: dict) -> tuple[int, int, int, int, float, str]:
        risk = str(patient.get("risk") or "").lower()
        risk_score = 2 if risk in {"high", "高"} else 1 if risk in {"medium", "中"} else 0
        spo2 = patient.get("spo2")
        low_spo2 = 1 if isinstance(spo2, (int, float)) and spo2 < 92 else 0
        return (
            int(patient.get("alerts") or 0),
            int(patient.get("news2") or 0),
            low_spo2,
            risk_score,
            -float(patient.get("spo2") or 100),
            str(patient.get("patient_id") or ""),
        )

    ordered = sorted(summaries, key=_priority_score, reverse=True)
    top_patients = ordered[:3]
    reasoning = "按告警、NEWS2、低氧和风险等级排序"

    if explain and summaries:
        try:
            from zhenhu.inpatient.agent.llm_utils import get_provider_for_node, safe_llm_invoke
            import json as _json

            provider = get_provider_for_node("ward_priority")
            prompt = (
                "你是病房主治医生。以下是当前在院患者摘要。请对既定规则排序的结果生成"
                "一段简短、可读的告警归并说明，说明每位患者的主要关注原因和相近告警如何合并理解。"
                "不得调整优先级，不得提出医嘱或处置决定。\n\n患者数据:\n" +
                _json.dumps(summaries, ensure_ascii=False)[:2000] +
                "\n\n返回JSON: {\"priority\": [\"patient_id1\", \"patient_id2\", \"patient_id3\"], \"reasoning\": \"按告警归并后的80字内关注说明，必须说明规则排序不变\"}"
            )
            result = await safe_llm_invoke(provider, prompt, timeout=15.0, retries=0, caller="ward_priority")
            if result:
                raw = result.get("response") or result.get("priority", "")
                if isinstance(raw, str) and raw.strip().startswith("{"):
                    parsed = _json.loads(raw)
                else:
                    parsed = result
                llm_reasoning = parsed.get("reasoning", "") if isinstance(parsed, dict) else ""
                if llm_reasoning:
                    reasoning = llm_reasoning
        except Exception:
            pass

    return UnifiedResponse(data={
        "total": len(summaries),
        "top_patients": top_patients,
        "reasoning": reasoning,
    })


# ═══════════════════════════════════════════════
# v0.3: 医生工作台总览 — 患者列表/待审核/告警
# ═══════════════════════════════════════════════

def _load_all_patient_states(user: dict) -> dict[str, tuple[float, dict]]:
    """加载全量患者状态。先从内存取，再从后端补。"""
    from .state_store import _store, _get_ttl, _backend
    ttl = _get_ttl()
    now = time.time()
    result = {}
    from ..services.patient_access import can_access_patient_state, iter_accessible_patient_states

    for pid, ts, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=ttl
    ):
        if can_access_patient_state(state, user):
            result[pid] = (ts, state)
    # 补充后端数据(内存未命中的)
    try:
        if hasattr(_backend, 'load_all'):
            loaded = _backend.load_all(ttl)
            for pid, (ts, state) in loaded.items():
                if pid not in result and can_access_patient_state(state, user):
                    result[pid] = (ts, state)
    except Exception:
        pass
    return result

@router.get("/patients")
async def get_ward_patients(request: Request, department: str = ""):
    """医生工作台 — 我科室的患者列表。

    按病种 + NEWS2 + 风险等级排序返回。
    department 为空时取请求头 x-department。
    """
    if not department:
        user = getattr(request.state, "user_info", {})
        department = user.get("department", "")
    if not department:
        return UnifiedResponse(data={
            "department": "",
            "patients": [],
            "count": 0,
            "summary": {"total": 0, "high_risk": 0, "news2_high": 0, "discharge_ready": 0},
            "hint": "未指定科室",
        })

    rows = _load_all_patient_states(getattr(request.state, "user_info", {}))
    patients = []
    for pid, (updated_at, state) in rows.items():
        tpl = (state.get("disease_template") or {})
        patient_data = (state.get("patient_data") or {})
        dept = tpl.get("department", "")
        if dept and dept != department:
            continue
        if not dept:
            dept = department  # fallback

        dc = state.get("discharge_criteria_check") or {}
        patients.append({
            "patient_id": pid,
            "name": patient_data.get("name") or tpl.get("name", pid),
            "disease": tpl.get("disease_id", ""),
            "department": dept,
            "risk_level": state.get("risk_level", "?"),
            "news2_score": state.get("news2_score"),
            "phase": state.get("current_step") or state.get("phase", "?"),
            "discharge_ready": dc.get("all_met", False),
            "alert_count": len(state.get("clinical_alerts") or []),
            "updated_at": updated_at,
        })

    patients.sort(key=lambda p: (
        -(p["news2_score"] or 0),           # NEWS2 高优先
        0 if p["risk_level"] == "高" else 1 if p["risk_level"] == "中" else 2,  # 风险高优先
        p["name"],
    ))

    return UnifiedResponse(data={
        "department": department,
        "patients": patients,
        "count": len(patients),
        "summary": {
            "total": len(patients),
            "high_risk": sum(1 for p in patients if p["risk_level"] == "高"),
            "news2_high": sum(1 for p in patients if (p["news2_score"] or 0) >= 5),
            "discharge_ready": sum(1 for p in patients if p["discharge_ready"]),
        },
    })


@router.get("/pending")
async def get_ward_pending(request: Request, department: str = ""):
    """医生工作台 — 待审核项汇总。

    返回: DDx 确认/用药确认/出院签字的待办列表。
    """
    if not department:
        user = getattr(request.state, "user_info", {})
        department = user.get("department", "")
    if not department:
        return UnifiedResponse(data={
            "department": "",
            "pending": [],
            "count": 0,
            "summary": {
                "total_patients": 0,
                "total_items": 0,
                "ddx_pending": 0,
                "med_pending": 0,
                "discharge_pending": 0,
            },
        })

    rows = _load_all_patient_states(getattr(request.state, "user_info", {}))
    pending = []
    for pid, (_, state) in rows.items():
        tpl = (state.get("disease_template") or {})
        patient_data = (state.get("patient_data") or {})
        dept = tpl.get("department", "")
        if dept and dept != department:
            continue

        # Only expose checkpoints the review endpoint can actually resume.
        # The earlier heuristic queue could present a DDx/medication row that
        # had no pending_review state, which made the doctor-facing action
        # unexecutable and encouraged clients to submit a guessed review type.
        pending_review = state.get("pending_review")
        review_type = pending_review.get("type") if isinstance(pending_review, dict) else None
        review_id = pending_review.get("review_id", "") if isinstance(pending_review, dict) else ""
        item_map = {
            "doctor_confirm": ("ddx_confirm", "入院诊断确认"),
            "med_confirm": ("med_confirm", "用药确认"),
            "discharge_sign": ("discharge_sign", "出院签字"),
        }
        items = []
        if review_type in item_map:
            item_type, label = item_map[review_type]
            items.append({
                "type": item_type,
                "label": label,
                "review_type": review_type,
                "review_id": review_id,
                "payload": pending_review.get("payload", {}),
            })

        if items:
            pending.append({
                "patient_id": pid,
                "name": patient_data.get("name") or tpl.get("name", pid),
                "disease": tpl.get("disease_id", ""),
                "phase": state.get("current_step") or state.get("phase", "?"),
                "state_version": state.get("state_version", 0),
                "items": items,
            })

    return UnifiedResponse(data={
        "department": department,
        "pending": pending,
        "count": len(pending),
        "summary": {
            "total_patients": len(pending),
            "total_items": sum(len(p["items"]) for p in pending),
            "ddx_pending": sum(1 for p in pending if any(i["type"] == "ddx_confirm" for i in p["items"])),
            "med_pending": sum(1 for p in pending if any(i["type"] == "med_confirm" for i in p["items"])),
            "discharge_pending": sum(1 for p in pending if any(i["type"] == "discharge_sign" for i in p["items"])),
        },
    })


@router.get("/workspace/alerts")
async def get_ward_alerts(request: Request, department: str = ""):
    """医生工作台 — 全科告警汇总。

    红色(高危)优先，黄色其次。
    """
    if not department:
        user = getattr(request.state, "user_info", {})
        department = user.get("department", "")
    if not department:
        return UnifiedResponse(data={
            "department": "",
            "alerts": [],
            "count": 0,
            "summary": {"total": 0, "red": 0, "yellow": 0},
        })

    rows = _load_all_patient_states(getattr(request.state, "user_info", {}))
    alerts = []
    for pid, (_, state) in rows.items():
        tpl = (state.get("disease_template") or {})
        patient_data = (state.get("patient_data") or {})
        dept = tpl.get("department", "")
        if dept and dept != department:
            continue

        raw_alerts = state.get("clinical_alerts") or []
        conflicts = state.get("_conflicts") or []
        for a in canonicalize_alerts(raw_alerts) + [canonicalize_alert(item) for item in conflicts]:
            severity = (
                "🔴" if a["severity"] == "critical" or any(k in a["message"] for k in ("高危", "出血", "禁忌", "紧急", "冲突"))
                else "🟡" if any(k in str(a) for k in ("注意", "监测", "调整"))
                else "🔵"
            )
            alerts.append({
                "patient_id": pid,
                "name": patient_data.get("name") or tpl.get("name", pid),
                "alert": a,
                "severity": severity,
            })

    alerts.sort(key=lambda a: 0 if a["severity"] == "🔴" else 1 if a["severity"] == "🟡" else 2)

    return UnifiedResponse(data={
        "department": department,
        "alerts": alerts,
        "count": len(alerts),
        "summary": {
            "total": len(alerts),
            "red": sum(1 for a in alerts if a["severity"] == "🔴"),
            "yellow": sum(1 for a in alerts if a["severity"] == "🟡"),
        },
    })
