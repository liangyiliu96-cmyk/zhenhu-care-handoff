"""病区总览端点 — GET /ward/overview
医生查房第一眼：所有患者的状态卡片概览。
纯 state_store 聚合读取，不经过 graph。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..schemas import UnifiedResponse
from ..services.clinical_alerts import canonicalize_alerts, is_critical_alert

router = APIRouter(prefix="/ward", tags=["ward"])


@router.get("/overview")
async def get_ward_overview(request: Request, phase: str | None = None, by: str | None = None):
    """返回病区所有患者概览。

    - ?phase=monitoring: 按阶段筛选
    - ?by=department: 按科室分组返回
    
    每个患者返回：patient_id, name, disease, phase, risk_level, 
    round_count, 最新体征摘要, 待审核状态, 告警数量
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    patients = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):

        p_phase = state.get("phase", "unknown")
        if phase and p_phase != phase:
            continue

        vs = state.get("vital_signs", []) or []
        latest_vs = vs[-1] if vs else {}
        alerts = state.get("clinical_alerts", []) or []
        tpl = state.get("disease_template", {}) or {}

        patients.append({
            "patient_id": pid,
            "name": (state.get("patient_data", {}) or {}).get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "unknown"),
            "department": tpl.get("department", "未知"),
            "phase": p_phase,
            "risk_level": state.get("risk_level", "unknown"),
            "round_count": state.get("round_count", 0),
            "discharge_decision": state.get("discharge_decision"),
            "latest_vital_signs": {
                k: latest_vs.get(k) for k in
                ("systolic_mmhg", "diastolic_mmhg", "heart_rate", "spo2", "temperature")
                if latest_vs.get(k) is not None
            },
            "has_pending_review": bool(state.get("pending_review")),
            "pending_review_type": (state.get("pending_review") or {}).get("type"),
            "alert_count": len(alerts),
            "latest_alerts": alerts[-3:],
            "document_chain_length": len(state.get("document_chain", [])),
        })

    # 按优先级排序
    priority = {"pending": 0, "high": 1, "medium": 2, "low": 3}
    patients.sort(key=lambda p: (
        0 if p["has_pending_review"] else 1,
        priority.get(p["risk_level"], 4),
    ))

    # 按科室分组
    if by == "department":
        departments: dict[str, dict] = {}
        for p in patients:
            dept = p.get("department", "未知")
            if dept not in departments:
                departments[dept] = {"name": dept, "total": 0, "high_risk": 0,
                                      "pending_review": 0, "patients": []}
            d = departments[dept]
            d["total"] += 1
            if p["risk_level"] == "high":
                d["high_risk"] += 1
            if p["has_pending_review"]:
                d["pending_review"] += 1
            d["patients"].append(p)

        # 科室按高危+待审数排序
        dept_list = sorted(departments.values(),
                           key=lambda d: (d["high_risk"] + d["pending_review"]), reverse=True)

        return UnifiedResponse(data={
            "total_patients": len(patients),
            "total_departments": len(dept_list),
            "pending_reviews": sum(d["pending_review"] for d in dept_list),
            "departments": dept_list,
        })

    return UnifiedResponse(data={
        "total": len(patients),
        "pending_reviews": sum(1 for p in patients if p["has_pending_review"]),
        "by_risk": {
            "high": sum(1 for p in patients if p["risk_level"] == "high"),
            "medium": sum(1 for p in patients if p["risk_level"] == "medium"),
            "low": sum(1 for p in patients if p["risk_level"] == "low"),
        },
        "patients": patients,
    })


@router.get("/alerts")
async def get_ward_alerts(request: Request, severity: str | None = None):
    """病区告警总览 — 所有患者的 clinical_alerts 聚合。

    可选 ?severity=critical 筛选危急值告警。
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    all_alerts = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue

        alerts = state.get("clinical_alerts", []) or []
        if not alerts:
            continue

        p_data = state.get("patient_data", {}) or {}
        tpl = state.get("disease_template", {}) or {}

        for alert in canonicalize_alerts(alerts):
            is_critical = isinstance(alert, str) and "[危急值]" in alert
            if isinstance(alert, dict):
                is_critical = is_critical_alert(alert)
            if severity == "critical" and not is_critical:
                continue

            all_alerts.append({
                "patient_id": pid,
                "patient_name": p_data.get("name", pid[:10]),
                "disease": tpl.get("name") or tpl.get("disease_id", "unknown"),
                "risk_level": state.get("risk_level"),
                "alert": alert,
                "is_critical": is_critical,
                "phase": state.get("phase"),
            })

    # 危急值优先
    all_alerts.sort(key=lambda a: (not a["is_critical"], a["patient_name"]))

    return UnifiedResponse(data={
        "total": len(all_alerts),
        "critical": sum(1 for a in all_alerts if a["is_critical"]),
        "patients_with_alerts": len(set(a["patient_id"] for a in all_alerts)),
        "alerts": all_alerts,
    })


@router.get("/vitals")
async def get_ward_vitals(request: Request, vital: str = Query("spo2", description="对比的体征: spo2/systolic/heart_rate/temperature")):
    """多患者体征对比 — 病区交班用。

    返回每个患者最近 3 次体征测量值，按趋势方向标注。
    可选 vital 参数指定对比指标。
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    patients = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue

        p_data = state.get("patient_data", {}) or {}
        tpl = state.get("disease_template", {}) or {}
        vs = state.get("vital_signs", []) or []

        recent = vs[-3:]
        values = []
        for v in recent:
            if vital == "spo2":
                val = v.get("spo2")
            elif vital == "systolic":
                val = f"{v.get('systolic_mmhg','?')}/{v.get('diastolic_mmhg','?')}"
            elif vital == "heart_rate":
                val = v.get("heart_rate")
            elif vital == "temperature":
                val = v.get("temperature")
            else:
                val = v.get("spo2")
            values.append(val)

        # 趋势计算
        trend = "stable"
        if len(values) >= 2:
            try:
                v0 = float(values[0]) if not isinstance(values[0], str) else float(str(values[0]).split("/")[0])
                v1 = float(values[-1]) if not isinstance(values[-1], str) else float(str(values[-1]).split("/")[0])
                if v1 > v0 * 1.05:
                    trend = "improving"
                elif v1 < v0 * 0.95:
                    trend = "declining"
            except (ValueError, TypeError):
                pass

        patients.append({
            "patient_id": pid,
            "name": p_data.get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "unknown"),
            "risk_level": state.get("risk_level"),
            "vital_values": values,
            "trend": trend,
            "alert_count": len(state.get("clinical_alerts", []) or []),
        })

    # 恶化优先
    trend_order = {"declining": 0, "stable": 1, "improving": 2}
    patients.sort(key=lambda p: trend_order.get(p["trend"], 1))

    return UnifiedResponse(data={
        "total": len(patients),
        "vital": vital,
        "summary": {
            "improving": sum(1 for p in patients if p["trend"] == "improving"),
            "stable": sum(1 for p in patients if p["trend"] == "stable"),
            "declining": sum(1 for p in patients if p["trend"] == "declining"),
        },
        "patients": patients,
    })


@router.get("/trends")
async def get_ward_trends(request: Request):
    """病区趋势总览 — 交班时扫一眼所有患者的恶化/改善情况。"""
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    patients = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue

        p_data = state.get("patient_data", {}) or {}
        tpl = state.get("disease_template", {}) or {}
        vs = state.get("vital_signs", []) or []

        # 计算各指标趋势
        def _calc_dir(field):
            vals = [v.get(field) for v in vs[-6:] if v.get(field) is not None]
            if len(vals) < 2:
                return "—"
            f = sum(vals[: len(vals) // 2]) / max(1, len(vals) // 2)
            s = sum(vals[len(vals) // 2 :]) / max(1, len(vals) - len(vals) // 2)
            if s > f * 1.03:
                return "↑"
            if s < f * 0.97:
                return "↓"
            return "→"

        latest = vs[-1] if vs else {}
        patients.append({
            "patient_id": pid,
            "name": p_data.get("name", pid[:10]),
            "disease": tpl.get("name") or tpl.get("disease_id", "?"),
            "risk": state.get("risk_level"),
            "round": state.get("round_count", 0),
            "bp_sys": f"{latest.get('systolic_mmhg', '?')}/{latest.get('diastolic_mmhg', '?')}",
            "bp_trend": _calc_dir("systolic_mmhg"),
            "spo2": latest.get("spo2", "?"),
            "spo2_trend": _calc_dir("spo2"),
            "hr": latest.get("heart_rate", "?"),
            "hr_trend": _calc_dir("heart_rate"),
            "temp": latest.get("temperature", "?"),
            "temp_trend": _calc_dir("temperature"),
            "alerts": len(state.get("clinical_alerts", []) or []),
        })

    # 恶化优先排序
    patients.sort(key=lambda p: (
        1 if "↓" in (p["bp_trend"], p["spo2_trend"]) else 2,
        -p["alerts"],
    ))

    return UnifiedResponse(data={
        "total": len(patients),
        "deteriorating": sum(1 for p in patients if p["bp_trend"] == "↓" or p["spo2_trend"] == "↓"),
        "patients": patients,
    })


@router.get("/lab-summary")
async def get_ward_lab_summary(request: Request, department: str | None = None):
    """病区检验异常总览 — 所有患者的异常检验结果汇总。
    可选 ?department=心内科 按科室筛选。
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    abnormal = []
    depts_seen = set()

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):
        if state.get("phase") in ("discharge", "confirm", "review"):
            continue

        p_data = state.get("patient_data", {}) or {}
        tpl = state.get("disease_template", {}) or {}
        dept = tpl.get("department", "未知")
        depts_seen.add(dept)

        if department and dept != department:
            continue

        labs = state.get("lab_results", []) or []
        lab_refs = tpl.get("lab_reference", {}) or {}

        for lab in labs:
            name = lab.get("name", "")
            ref = lab_refs.get(name, {})
            if not ref:
                continue
            try:
                val = float(lab.get("value", 0))
            except (ValueError, TypeError):
                continue
            lo, hi = ref.get("low"), ref.get("high")
            is_high = hi is not None and val > hi
            is_low = lo is not None and val < lo
            if not is_high and not is_low:
                continue
            abnormal.append({
                "patient_id": pid,
                "patient_name": p_data.get("name", pid[:10]),
                "disease": tpl.get("name") or tpl.get("disease_id", "?"),
                "department": dept,
                "risk": state.get("risk_level"),
                "lab_name": name,
                "value": val,
                "unit": lab.get("unit", ""),
                "ref_range": f"{lo}-{hi}",
                "direction": "high" if is_high else "low",
                "deviation": round(abs(val - (hi if is_high else lo)), 1),
            })

    # 偏差大的优先
    abnormal.sort(key=lambda a: -a["deviation"])

    return UnifiedResponse(data={
        "total": len(abnormal),
        "patients_affected": len(set(a["patient_id"] for a in abnormal)),
        "departments_affected": len(depts_seen),
        "abnormal_labs": abnormal,
    })


# ═══════════════════════════════════════════════════════════
# #3: 科室工作负载面板
# ═══════════════════════════════════════════════════════════

@router.get("/workload")
async def get_ward_workload(request: Request, department: str | None = None):
    """科室工作负载面板 — 护士长/科主任视角。

    按科室统计: 患者数、高危比例、待审堆积、监测超时、告警密度。
    可选 ?department=心内科 筛选单个科室。
    """
    from .state_store import _store, _get_ttl
    import time

    ttl = _get_ttl()
    now = time.time()
    dept_stats: dict[str, dict] = {}

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(list(_store.items()), user, now=now, ttl=ttl):

        tpl = state.get("disease_template", {}) or {}
        dept = tpl.get("department", "未知")

        # 全量采集（不在此处筛选，保留全科基准用于排名和均值计算）
        if dept not in dept_stats:
            dept_stats[dept] = {
                "department": dept,
                "total": 0,
                "active": 0,        # monitoring 阶段
                "high_risk": 0,
                "pending_review": 0,
                "vital_overdue": 0,  # 体征超时（超过监测间隔）
                "total_alerts": 0,
                "total_rounds": 0,
            }

        stats = dept_stats[dept]
        stats["total"] += 1

        phase = state.get("phase", "")
        if phase not in ("discharge", "confirm", "review"):
            stats["active"] += 1

        if state.get("risk_level") == "high":
            stats["high_risk"] += 1
        if state.get("pending_review"):
            stats["pending_review"] += 1
        stats["total_rounds"] += state.get("round_count", 0)
        stats["total_alerts"] += len(state.get("clinical_alerts", []) or [])

        # 体征超时检测
        vs = state.get("vital_signs", []) or []
        monitoring_interval = tpl.get("monitoring_interval_hours")
        if monitoring_interval and vs:
            last_vs = vs[-1]
            last_time = last_vs.get("timestamp", "")
            if last_time:
                try:
                    from datetime import datetime
                    last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
                    if (now - last_dt.timestamp()) / 3600 > monitoring_interval:
                        stats["vital_overdue"] += 1
                except Exception:
                    pass

    # 计算派生指标 + 排序
    result = []
    for dept, s in dept_stats.items():
        active = max(s["active"], 1)
        s["high_risk_ratio"] = round(s["high_risk"] / max(s["total"], 1), 2)
        s["avg_alerts_per_patient"] = round(s["total_alerts"] / max(active, 1), 1)
        s["overdue_ratio"] = round(s["vital_overdue"] / max(active, 1), 2)
        result.append(s)

    # 负载排序: 高危+待审+超时综合
    result.sort(key=lambda s: (
        s["high_risk"] + s["pending_review"] * 2 + s["vital_overdue"]
    ), reverse=True)

    response_data = {
        "total_departments": len(result),
        "total_active": sum(s["active"] for s in result),
        "total_high_risk": sum(s["high_risk"] for s in result),
        "total_pending": sum(s["pending_review"] for s in result),
        "departments": result if not department else [s for s in result if s["department"] == department],
    }

    # 单科详情: 基于全科排名 + 与全院均值偏差
    if department and len(result) >= 1:
        dept_data = next((s for s in result if s["department"] == department), None)
        if dept_data:
            n = len(result)
            _load = lambda s: s["high_risk"] + s["pending_review"] * 2 + s["vital_overdue"]
            rank_load = sum(1 for s in result if _load(s) > _load(dept_data)) + 1
            rank_risk = sum(1 for s in result
                            if s["high_risk_ratio"] > dept_data["high_risk_ratio"]) + 1

            def _avg(key):
                return round(sum(s.get(key, 0) for s in result) / max(n, 1), 2)

            avg_risk = _avg("high_risk_ratio")
            response_data["department_detail"] = {
                "department": department,
                "ranking": {
                    "load": f"{rank_load}/{n}",
                    "load_percentile": round((1 - rank_load / n) * 100),
                    "risk": f"{rank_risk}/{n}",
                },
                "vs_average": {
                    "high_risk_ratio": round(dept_data["high_risk_ratio"] - avg_risk, 2),
                    "avg_alerts_per_patient": round(dept_data["avg_alerts_per_patient"] - _avg("avg_alerts_per_patient"), 1),
                    "overdue_ratio": round(dept_data["overdue_ratio"] - _avg("overdue_ratio"), 2),
                    "active_patients": dept_data["active"] - round(_avg("active")),
                },
                "summary": (
                    f"{department} 在全院 {n} 个科室中负载排第 {rank_load} "
                    f"(前 {round(rank_load/n*100)}%)，"
                    f"高危比 {'高于' if dept_data['high_risk_ratio'] > avg_risk else '低于'}均值 "
                    f"{abs(dept_data['high_risk_ratio'] - avg_risk):.0%}"
                ),
            }

    return UnifiedResponse(data=response_data)


# ═══════════════════════════════════════════════════════════
# 方案2: 病区 AI 实时摘要
# ═══════════════════════════════════════════════════════════

import time as _time

_ai_summary_cache: dict = {"text": "", "ts": 0.0}
_AI_CACHE_TTL = 30  # 30 秒缓存


@router.get("/ai-summary")
async def get_ward_ai_summary(request: Request, department: str | None = None):
    """病区 AI 自然语言摘要 — 聚合全科患者状态生成。

    30 秒缓存，适用于大屏自动刷新。
    可选 ?department=心内科 只看单科。
    """
    global _ai_summary_cache
    now = _time.time()
    cache_key = department or "__all__"
    if _ai_summary_cache.get("key") == cache_key and now - _ai_summary_cache.get("ts", 0) < _AI_CACHE_TTL:
        return UnifiedResponse(data={"summary": _ai_summary_cache["text"], "cached": True})

    from .state_store import _store, _get_ttl
    ttl = _get_ttl()
    now_ts = _time.time()
    patients_summary = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now_ts, ttl=ttl
    ):
        phase = state.get("phase", "?")
        if phase in ("discharge", "confirm", "review"):
            continue
        dept = (state.get("disease_template") or {}).get("department", "未知")
        if department and dept != department:
            continue

        risk = state.get("risk_level", "?")
        news2 = state.get("news2_score")
        alerts = len(state.get("clinical_alerts", []) or [])
        has_pending = bool(state.get("pending_review"))
        name = tpl_name = (state.get("disease_template") or {}).get("name") or \
                          (state.get("disease_template") or {}).get("disease_id") or pid[:10]
        patients_summary.append(
            f"{name}({risk}风险 NEWS2={news2} 告警{alerts}条"
            f"{' 待审' if has_pending else ''})"
        )

    if not patients_summary:
        return UnifiedResponse(data={"summary": "当前病区无活跃患者。", "cached": False})

    try:
        from ..agent.config import get_cached_provider
        from ..agent.llm_utils import safe_llm_invoke
        provider = get_cached_provider()
        prompt = (
            f"病区实时状态: 共{len(patients_summary)}名患者。\n"
            + "\n".join(patients_summary) +
            f"\n\n请用100字以内中文生成病区摘要，格式：总体概况1-2句 + 需重点关注患者1-3人。不要前缀。"
        )
        llm_result = await safe_llm_invoke(provider, prompt, timeout=10.0)
        summary = (llm_result or {}).get("response", "") if llm_result else ""
        if not summary:
            high_risk = [p for p in patients_summary if "high" in p.lower() or "高危" in p]
            summary = f"病区共{len(patients_summary)}名患者。" + (
                f"重点关注: {'; '.join(h for h in high_risk[:3])}" if high_risk
                else "已出院/确认阶段。"
            )
    except Exception:
        high_risk = [p for p in patients_summary if "high" in p.lower() or "高危" in p]
        summary = f"病区共{len(patients_summary)}名患者。" + (
            f"重点关注: {'; '.join(h for h in high_risk[:3])}" if high_risk
            else "体征稳定。"
        )

    _ai_summary_cache = {"key": cache_key, "text": summary, "ts": now}
    return UnifiedResponse(data={"summary": summary, "cached": False, "last_updated": now})



# ═══════════════════════════════════════════════════════════
# 方案3: 交班看板
# ═══════════════════════════════════════════════════════════

@router.get("/shift-report")
async def get_ward_shift_report(request: Request, department: str | None = None):
    """交班报告 — 聚合全科患者的 shift_summary + 出院状态。

    可选 ?department=心内科 只看单科。
    """
    from .state_store import _store, _get_ttl
    ttl = _get_ttl()
    now = _time.time()
    high_focus, stable, discharge_today = [], [], []
    departments_seen = set()

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=ttl
    ):
        dept = (state.get("disease_template") or {}).get("department", "未知")
        departments_seen.add(dept)
        if department and dept != department:
            continue

        phase = state.get("phase", "?")
        risk = state.get("risk_level", "?")
        shift = state.get("shift_summary") or ""
        news2 = state.get("news2_score")
        name = (state.get("disease_template") or {}).get("name") or \
               (state.get("disease_template") or {}).get("disease_id") or pid[:10]
        entry = {
            "patient_id": pid, "name": name, "risk": risk,
            "news2": news2, "shift_summary": shift,
            "alerts": len(state.get("clinical_alerts", []) or []),
            "handoff_acknowledged": state.get("handoff_acknowledged"),
        }

        if phase in ("confirm", "review"):
            discharge_today.append(entry)
        elif risk == "high" or (news2 is not None and news2 >= 5) or entry["alerts"] >= 3:
            high_focus.append(entry)
        else:
            stable.append(entry)

    # AI 交班要点
    ai_report = ""
    if high_focus:
        try:
            from ..agent.config import get_cached_provider
            from ..agent.llm_utils import safe_llm_invoke
            provider = get_cached_provider()
            hf_text = "; ".join(
                f"{h['name']}({h['risk']} NEWS2={h['news2']} alerts={h['alerts']})"
                for h in high_focus[:5]
            )
            prompt = (
                f"交班报告: 重点关注{len(high_focus)}人: {hf_text}。"
                f"今日出院{len(discharge_today)}人。"
                f"请用50字以内中文生成交班要点，不要前缀。"
            )
            llm_result = await safe_llm_invoke(provider, prompt, timeout=10.0)
            ai_report = (llm_result or {}).get("response", "") if llm_result else ""
        except Exception:
            pass
    if not ai_report:
        ai_report = f"交班: 重点关注{len(high_focus)}人, 今日出院{len(discharge_today)}人, 稳定{len(stable)}人。"

    return UnifiedResponse(data={
        "departments": sorted(departments_seen),
        "total": len(high_focus) + len(stable) + len(discharge_today),
        "today_discharge": len(discharge_today),
        "high_focus": high_focus,
        "stable": stable,
        "discharge_today": discharge_today,
        "ai_report": ai_report,
    })


# ═══════════════════════════════════════════════════════════
# 管理 AI 洞察
# ═══════════════════════════════════════════════════════════

@router.get("/insights")
async def get_ward_insights(request: Request):
    """管理洞察 — 病区趋势 + 运营建议。聚合 workload + alerts + overdue。"""
    from .state_store import _store, _get_ttl
    ttl = _get_ttl()
    now = _time.time()
    total_active = high_risk = pending = overdue_vs = total_alerts = 0
    dept_stats: dict[str, int] = {}

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=ttl
    ):
        if state.get("phase", "?") in ("discharge", "confirm", "review"):
            continue
        dept = (state.get("disease_template") or {}).get("department", "未知")
        total_active += 1
        dept_stats[dept] = dept_stats.get(dept, 0) + 1
        if state.get("risk_level") == "high":
            high_risk += 1
        if state.get("pending_review"):
            pending += 1
        total_alerts += len(state.get("clinical_alerts", []) or [])

    top_dept = sorted(dept_stats.items(), key=lambda x: x[1], reverse=True)[:3]
    dept_text = ", ".join(f"{k}({v}人)" for k, v in top_dept)

    insight = f"病区共{total_active}活跃患者, {high_risk}高危, {pending}待审。"
    try:
        from ..agent.config import get_cached_provider
        from ..agent.llm_utils import safe_llm_invoke
        provider = get_cached_provider()
        prompt = (
            f"病区管理数据: 活跃{total_active}人, 高危{high_risk}, 待审{pending}, "
            f"总告警{total_alerts}, 科室: {dept_text}。"
            f"请用一句中文(40字内)给出病区管理建议。不要前缀。"
        )
        llm_result = await safe_llm_invoke(provider, prompt, timeout=8.0)
        llm_insight = (llm_result or {}).get("response", "")
        if llm_insight:
            insight = llm_insight
    except Exception:
        pass

    return UnifiedResponse(data={
        "insight": insight,
        "stats": {"total_active": total_active, "high_risk": high_risk,
                  "pending_review": pending, "total_alerts": total_alerts},
        "top_departments": [{"department": k, "patients": v} for k, v in top_dept],
    })


# ═══════════════════════════════════════════════════════════
# 医生查房访视顺序优化 (Agent + LLM)
# ═══════════════════════════════════════════════════════════

@router.get("/visit-order")
async def get_ward_visit_order(
    request: Request,
    explain: bool = Query(False, description="是否生成 LLM 查房顺序说明"),
):
    """医生查房访视顺序 — 基于临床紧急度排序 + LLM 解释原因。

    综合考虑: NEWS2 评分、体征恶化趋势、待审堆积、新检验结果。
    """
    from .state_store import _store, _get_ttl
    ttl = _get_ttl()
    now = _time.time()
    patients = []

    from ..services.patient_access import iter_accessible_patient_states
    user = getattr(request.state, "user_info", {})
    for pid, ts, state in iter_accessible_patient_states(
        list(_store.items()), user, now=now, ttl=ttl
    ):
        phase = state.get("phase", "?")
        if phase in ("discharge", "confirm", "review"):
            continue

        vs = state.get("vital_signs", []) or []
        latest = vs[-1] if vs else {}
        prev = vs[-3] if len(vs) >= 3 else (vs[0] if vs else {})
        name = (state.get("disease_template") or {}).get("name") or \
               (state.get("disease_template") or {}).get("disease_id") or pid[:10]

        # 恶化检测
        deteriorating = False
        try:
            if latest.get("spo2", 100) < prev.get("spo2", 100) - 2:
                deteriorating = True
            if latest.get("heart_rate", 80) > prev.get("heart_rate", 80) + 15:
                deteriorating = True
        except (TypeError, ValueError):
            pass

        patients.append({
            "patient_id": pid, "name": name,
            "risk": state.get("risk_level"),
            "news2": state.get("news2_score"),
            "alerts": len(state.get("clinical_alerts", []) or []),
            "has_pending": bool(state.get("pending_review")),
            "deteriorating": deteriorating,
            "spo2": latest.get("spo2"), "hr": latest.get("heart_rate"),
            "round_count": state.get("round_count", 0),
            "department": (state.get("disease_template") or {}).get("department", ""),
        })

    # 紧急度权重: NEWS2高危 +5, 恶化 +4, 待审 +3, 高危 +2, 告警数 +1
    def _urgency(p):
        s = 0
        if p["news2"] and p["news2"] >= 7: s += 5
        elif p["news2"] and p["news2"] >= 5: s += 3
        if p["deteriorating"]: s += 4
        if p["has_pending"]: s += 3
        if p["risk"] == "high": s += 2
        if p["spo2"] and p["spo2"] < 92: s += 2
        s += min(p["alerts"], 5)
        return s

    ordered = sorted(patients, key=_urgency, reverse=True)

    # 默认使用确定性说明，避免病区看板被可选 LLM 解释阻塞。
    reason = f"共{len(ordered)}名患者，按临床紧急度排序。"
    if explain and ordered:
        try:
            from ..agent.config import get_cached_provider
            from ..agent.llm_utils import safe_llm_invoke
            provider = get_cached_provider()
            top3 = ordered[:3]
            top_text = "; ".join(
                f"{p['name']}({p['risk']} NEWS2={p['news2']} alerts={p['alerts']}"
                f"{' 恶化' if p['deteriorating'] else ''}{' 待审' if p['has_pending'] else ''})"
                for p in top3
            )
            prompt = (
                f"查房访视顺序: 优先 {top_text}。共{len(ordered)}名患者。"
                f"请用一句中文(30字内)解释为什么按此顺序访视。不要前缀。"
            )
            llm_result = await safe_llm_invoke(provider, prompt, timeout=8.0)
            llm_reason = (llm_result or {}).get("response", "")
            if llm_reason:
                reason = llm_reason
        except Exception:
            pass

    return UnifiedResponse(data={
        "reason": reason,
        "total": len(ordered),
        "urgent": len([p for p in ordered if _urgency(p) >= 6]),
        "stable": len([p for p in ordered if _urgency(p) <= 1]),
        "visit_order": ordered,
    })
