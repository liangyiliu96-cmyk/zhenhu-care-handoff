"""NEWS2 早期预警 + qSOFA 脓毒症筛查 + VTE 预防 + 卒中抗栓 —— 纯规则计算节点。

NEWS2 (National Early Warning Score 2): NHS 标准，6 项体征 0-20 分
    0-4: 低风险(每4-6h复评)
    5-6: 中风险(紧急评估, 1h内)
    ≥7: 高风险(立即响应, 持续监测)

qSOFA (Quick SOFA): 床旁脓毒症筛查, ≥2 分高风险

VTE-1: CMS CMS108v14 静脉血栓栓塞预防检查（入院 24h 内）
STK-2: CMS CMS104v13/CMS71v14 卒中出院抗栓检查
"""

import logging
from pathlib import Path

from .config import get_cached_provider
from .llm_utils import deep_invoke
from .metrics import record
from . import prompts  # P1-1

logger = logging.getLogger("zhenhu.inpatient")


def _merge_evidence_citations(state: dict, citations: list[dict]) -> list[dict]:
    """Append new RAG citations while retaining a bounded evidence trail."""
    evidence = list(state.get("clinical_evidence", []) or [])
    citation_ids = {
        item.get("citation_id")
        for item in evidence
        if isinstance(item, dict) and item.get("citation_id")
    }
    for citation in citations:
        citation_id = citation.get("citation_id") if isinstance(citation, dict) else None
        if citation_id and citation_id not in citation_ids:
            evidence.append(citation)
            citation_ids.add(citation_id)
    return evidence[-20:]

# ── P2-2: NEWS2 阈值从 YAML 加载，缺失时回退硬编码 ──
_DEFAULT_NEWS2_RR = [(8, 3), (9, 1), (11, 1), (20, 0), (24, 2), (float("inf"), 3)]
_DEFAULT_NEWS2_SPO2_SCALE1 = [(91, 3), (93, 2), (95, 1), (float("inf"), 0)]
_DEFAULT_NEWS2_SPO2_SCALE2 = [(83, 3), (85, 2), (87, 1), (92, 0)]
_DEFAULT_NEWS2_TEMP = [(35.0, 3), (36.0, 1), (38.0, 0), (39.0, 1), (float("inf"), 2)]
_DEFAULT_NEWS2_SBP = [(90, 3), (100, 2), (110, 1), (219, 0), (float("inf"), 3)]
_DEFAULT_NEWS2_HR = [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2), (float("inf"), 3)]

_thresholds: dict | None = None


def _load_thresholds() -> dict:
    """懒加载 scoring_thresholds.yaml，失败回退硬编码默认值。"""
    global _thresholds
    if _thresholds is not None:
        return _thresholds

    yaml_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "scoring_thresholds.yaml"
    try:
        import json as _json_module
        import re
        _json = _json_module
        with open(yaml_path, encoding="utf-8") as f:
            raw = f.read()

        # 简单 YAML: 按节解析  news2: → rr: [...], spo2_scale1: [...]
        _thresholds = {}
        section = ""
        current_key = ""
        for line in raw.split("\n"):
            s = line.strip()
            # 去掉行尾注释和多余空格
            comment_pos = s.find("  #")
            if comment_pos > 0:
                s = s[:comment_pos].rstrip()
            if s.startswith("#") or not s: continue
            # 顶级 section (如 "news2:")
            if s.endswith(":") and not s.startswith("-") and not line.startswith("  "):
                section = s.rstrip(":").strip() + "_"
                continue
            # 子级 key
            if s.endswith(":") and not s.startswith("-"):
                current_key = section + s.rstrip(":").strip()
                _thresholds[current_key] = []
                continue
            # 列表项
            b = s.find("[")
            if b >= 0:
                item_text = s[b:].replace("'", '"').replace('"inf"', "1e999")
                try:
                    val, score = _json.loads(item_text)
                    val = float("inf") if val == 1e999 else float(val)
                    _thresholds.setdefault(current_key, []).append([val, int(score)])
                except: pass

        logger.info("_load_thresholds: loaded from %s", yaml_path)
    except Exception as e:
        logger.warning("_load_thresholds: YAML 加载失败 (%s)，使用硬编码默认值", e)
        _thresholds = {
            "news2_rr": _DEFAULT_NEWS2_RR,
            "news2_spo2_scale1": _DEFAULT_NEWS2_SPO2_SCALE1,
            "news2_spo2_scale2": _DEFAULT_NEWS2_SPO2_SCALE2,
            "news2_temp": _DEFAULT_NEWS2_TEMP,
            "news2_sbp": _DEFAULT_NEWS2_SBP,
            "news2_hr": _DEFAULT_NEWS2_HR,
        }
    return _thresholds


def _parse_simple_yaml(raw: str) -> dict:
    """极简 YAML 解析器：只解析 [[upper, score], ...] 格式的阈值表。"""
    import json as _json
    # 将 YAML 风格的 [...] 列表转为合法 JSON 再解析
    result = {}
    current_key = None
    current_list = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            # 保存上一段
            if current_key and current_list:
                result[current_key] = current_list
            current_key = stripped.rstrip(":").strip()
            current_list = []
            continue
        # 列表项: 处理 [val, score] 或 - [val, score]
        bracket_start = stripped.find("[")
        if bracket_start >= 0:
            item_text = stripped[bracket_start:].replace("'", '"')
            # 处理 "inf" → Infinity
            if '"inf"' in item_text:
                item_text = item_text.replace('"inf"', "1e999")  # 用大数代替 inf for JSON
            try:
                val, score = _json.loads(item_text)
                if val == 1e999:
                    val = float("inf")
                val = float(val)
                score = int(score)
                current_list.append([val, score])
            except (ValueError, _json.JSONDecodeError):
                pass

    if current_key and current_list:
        result[current_key] = current_list
    return result


def _score_range(value: float, table: list) -> int:
    """按阈值表查分。table 是 [(upper_bound, score), ...]，找到第一个 value <= upper_bound。"""
    for bound, score in table:
        if value <= bound:
            return score
    return 0


def _score_range_rev(value: float, table: list) -> int:
    """逆向查分（用于 SpO2 scale2 和 SBP）。"""
    for bound, score in table:
        if value <= bound:
            return score
    return 0


async def node_news2(state: dict) -> dict:
    """NEWS2 早期预警评分 — 每次监测循环执行。

    纯规则计算，不依赖 LLM。
    评分结果写入 clinical_alerts 和 state。
    """
    patient_id = state.get("patient_id", "unknown")
    vs = state.get("vital_signs", [])
    if not vs:
        return {}

    latest = vs[-1]

    # 1. 呼吸频率
    rr = latest.get("respiratory_rate")
    th = _load_thresholds()
    rr_score = _score_range(rr, th["news2_rr"]) if rr is not None else 0

    # 2. SpO2（默认用 scale1，COPD 用 scale2）
    spo2 = latest.get("spo2")
    spo2_score = 0
    if spo2 is not None:
        tpl = state.get("disease_template", {})
        is_copd = tpl.get("disease_id") == "copd" or "COPD" in tpl.get("name", "")
        if is_copd:
            spo2_score = _score_range_rev(spo2, th["news2_spo2_scale2"])
        else:
            spo2_score = _score_range(spo2, th["news2_spo2_scale1"])

    # 3. 体温
    temp = latest.get("temperature")
    temp_score = _score_range(temp, th["news2_temp"]) if temp is not None else 0

    # 4. 收缩压
    sbp = latest.get("systolic_mmhg") or latest.get("systolic")
    sbp_score = 0
    if sbp is not None:
        sbp_score = _score_range_rev(float(sbp), th["news2_sbp"])

    # 5. 心率
    hr = latest.get("heart_rate")
    hr_score = _score_range(hr, th["news2_hr"]) if hr is not None else 0

    # 6. 意识（从 patient_data 或 vital signs 获取）
    consciousness = 0  # 默认 Alert=0
    consciousness_data = latest.get("consciousness") or latest.get("gcs")
    if consciousness_data is not None:
        if isinstance(consciousness_data, str) and consciousness_data.lower() in ("v", "p", "u", "confused"):
            consciousness = 3
        elif isinstance(consciousness_data, (int, float)) and consciousness_data < 15:
            consciousness = 3

    total = rr_score + spo2_score + temp_score + sbp_score + hr_score + consciousness

    # 风险分级
    if total >= 7:
        risk = "high"
        action = "立即通知医生, 考虑转ICU, 持续监测"
    elif total >= 5:
        risk = "medium"
        action = "紧急评估, 1小时内通知医生"
    else:
        risk = "low"
        action = "常规4-6小时复评"

    alert = f"[NEWS2={total}] {risk}风险: RR={rr_score} SpO2={spo2_score} Temp={temp_score} SBP={sbp_score} HR={hr_score} CNS={consciousness} → {action}"

    logger.info("node_news2: patient=%s NEWS2=%d (%s)", patient_id, total, risk)

    record("news2")
    alerts = list(state.get("clinical_alerts", []) or [])
    evidence_citations = []
    if total >= 5:
        # ── #2: LLM 临床建议 ──
        suggestion = ""
        try:
            provider = get_cached_provider()
            sug_prompt = prompts.news2_suggestion_prompt(
                total, risk, str(rr), str(spo2), str(hr), str(sbp), str(temp)
            )
            sug_result = await deep_invoke(provider, sug_prompt, caller="shift_summary", timeout=8.0)
            suggestion = (sug_result or {}).get("response", "") if sug_result else ""
            evidence_citations = list((sug_result or {}).get("_rag_citations", []) or [])
        except Exception:
            pass
        if suggestion:
            alert += f" → 建议: {suggestion}"
        alerts.append(alert)

    chain = list(state.get("document_chain", []) or [])
    if total >= 5 and "news2_alert" not in chain:
        chain.append("news2_alert")

    return {
        "news2_score": total,
        "news2_risk": risk,
        "clinical_alerts": alerts,
        "clinical_evidence": _merge_evidence_citations(state, evidence_citations),
        "document_chain": chain,
    }


async def node_qsofa(state: dict) -> dict:
    """qSOFA 脓毒症筛查 — 每次监测循环执行。

    ≥2 分 → 高风险，需立即评估脓毒症并考虑抗生素。
    """
    patient_id = state.get("patient_id", "unknown")
    vs = state.get("vital_signs", [])
    if not vs:
        return {}

    latest = vs[-1]

    # 1. 呼吸频率 ≥22
    rr = latest.get("respiratory_rate")
    rr_pos = 1 if (rr is not None and rr >= 22) else 0

    # 2. 收缩压 ≤100
    sbp = latest.get("systolic_mmhg") or latest.get("systolic")
    sbp_pos = 1 if (sbp is not None and float(sbp) <= 100) else 0

    # 3. GCS <15
    gcs = latest.get("gcs")
    gcs_pos = 1 if (gcs is not None and gcs < 15) else 0

    total = rr_pos + sbp_pos + gcs_pos
    risk = "high" if total >= 2 else "low"
    action = "疑似脓毒症—立即血培养+乳酸+抗生素" if total >= 2 else ""

    if total >= 2:
        alert = f"[qSOFA={total}] {action}"
        logger.info("node_qsofa: patient=%s qSOFA=%d (HIGH)", patient_id, total)
    else:
        alert = None
        logger.info("node_qsofa: patient=%s qSOFA=%d", patient_id, total)

    record("qsofa")
    alerts = list(state.get("clinical_alerts", []) or [])
    evidence_citations = []
    if alert:
        # ── #2: LLM 临床建议 ──
        suggestion = ""
        try:
            provider = get_cached_provider()
            sug_prompt = prompts.qsofa_suggestion_prompt(
                total, str(rr), str(sbp), str(gcs)
            )
            sug_result = await deep_invoke(provider, sug_prompt, caller="shift_summary", timeout=8.0)
            suggestion = (sug_result or {}).get("response", "") if sug_result else ""
            evidence_citations = list((sug_result or {}).get("_rag_citations", []) or [])
        except Exception:
            pass
        if suggestion:
            alert += f" → 建议: {suggestion}"
        alerts.append(alert)

    chain = list(state.get("document_chain", []) or [])
    if total >= 2 and "qsofa_alert" not in chain:
        chain.append("qsofa_alert")

    return {
        "qsofa_score": total,
        "qsofa_risk": risk,
        "clinical_alerts": alerts,
        "clinical_evidence": _merge_evidence_citations(state, evidence_citations),
        "document_chain": chain,
    }


# ── VTE-1 / STK-2 质控节点 ──


async def node_vte_prophylaxis(state: dict) -> dict:
    """VTE-1 静脉血栓栓塞预防检查 — 入院 24h 内是否给予 VTE 预防。

    规则: CMS CMS108v14 简化版
    - 分母: ≥18岁住院患者（入院 phase 已通过）
    - 排除: 住院<2天 / 已有VTE诊断 / 舒适护理 / 精神疾病主诊
    - 分子: Day0-Day1 收到 抗凝药 or 下肢加压装置 or 有禁忌记录

    仅在 admission 阶段首次通过 doctor_confirm 后执行一次。
    """
    patient_id = state.get("patient_id", "unknown")
    chain = state.get("document_chain", [])

    # 只在入院确认后、首次监测前执行一次
    if "vte_check" in chain:
        return {}
    if "doctor_confirm_auto" not in chain and state.get("doctor_confirm_status") != "approved":
        return {}

    tpl = state.get("disease_template", {}) or {}
    p_data = state.get("patient_data", {}) or {}
    meds = state.get("medication_adjustments", []) or []
    allergies = state.get("allergies", []) or []

    # === 排除条件 ===
    # 1. 已有 VTE/DVT/PE 诊断
    ddx = state.get("ddx_list", []) or []
    vte_keywords = ["VTE", "DVT", "深静脉血栓", "肺栓塞", "PE", "pulmonary embolism", "venous thromboembolism"]
    has_vte = any(
        any(kw.lower() in (d.get("diagnosis", "") or "").lower() for kw in vte_keywords)
        for d in ddx
    )
    if has_vte:
        logger.info("node_vte_prophylaxis: patient=%s excluded (existing VTE diagnosis)", patient_id)
        return {"document_chain": chain + ["vte_check"]}

    # 2. 精神疾病主诊
    disease_name = (tpl.get("name") or tpl.get("disease_id", "")).lower()
    psych_keywords = ["mental", "schizophrenia", "精神", "bipolar"]
    if any(kw in disease_name for kw in psych_keywords):
        return {"document_chain": chain + ["vte_check"]}

    # === 检查 VTE 预防 ===
    # 抗凝药关键词（肝素类、华法林类、Factor Xa 抑制剂等）
    anticoagulant_kw = [
        "肝素", "heparin", "低分子肝素", "LMWH", "enoxaparin", "依诺肝素",
        "华法林", "warfarin", "利伐沙班", "rivaroxaban", "阿哌沙班", "apixaban",
        "达比加群", "dabigatran", "磺达肝癸钠", "fondaparinux",
    ]

    has_anticoagulant = False
    for m in meds:
        if not isinstance(m, dict):
            continue
        drug = str(m.get("drug") or m.get("medication") or "").lower()
        if any(kw.lower() in drug for kw in anticoagulant_kw):
            has_anticoagulant = True
            break

    # 检查是否有出血禁忌
    bleeding_risk_kw = ["出血", "bleeding", "hemorrhage", "gi bleed", "消化道出血"]
    has_bleeding_risk = disease_name and any(kw in disease_name for kw in bleeding_risk_kw)

    alerts = list(state.get("clinical_alerts", []) or [])

    if has_anticoagulant:
        logger.info("node_vte_prophylaxis: patient=%s VTE prophylaxis OK (anticoagulant)", patient_id)
        return {
            "document_chain": chain + ["vte_check"],
        }
    elif has_bleeding_risk:
        # 出血高风险 → 建议机械预防
        alert = "[VTE-1] VTE预防: 出血风险患者, 建议下肢加压装置或弹力袜"
        alerts.append(alert)
        logger.info("node_vte_prophylaxis: patient=%s bleeding risk, recommend mechanical", patient_id)
        return {
            "document_chain": chain + ["vte_check"],
            "clinical_alerts": alerts,
        }
    else:
        # 未预防也无禁忌 → 质控缺陷
        alert = "[VTE-1] VTE预防缺失: 入院24h内未给予药物或机械预防, 建议立即评估Padua评分并启动预防"
        alerts.append(alert)
        logger.info("node_vte_prophylaxis: patient=%s VTE prophylaxis MISSING", patient_id)
        return {
            "document_chain": chain + ["vte_check"],
            "clinical_alerts": alerts,
        }


async def node_stroke_antithrombotic(state: dict) -> dict:
    """STK-2/STK-3 卒中出院抗栓检查 — 缺血性卒中患者出院时是否给了抗血小板/抗凝药。

    规则: CMS CMS104v13 + CMS71v14 简化版
    - 仅在 discharge 阶段执行，出院签字前检查
    - 卒中/Afib患者 → 必须给抗栓药
    """
    patient_id = state.get("patient_id", "unknown")
    chain = state.get("document_chain", [])

    # 只在出院签字阶段执行一次（idempotent guard）
    if "stroke_at_check" in chain:
        return {}

    tpl = state.get("disease_template", {}) or {}
    disease_name = (tpl.get("name") or tpl.get("disease_id", "")).lower()

    # 只对卒中相关病种执行（全部小写，与 .lower() 比较）
    stroke_kw = ["stroke", "卒中", "cerebral", "ischemic", "脑梗", "tia"]
    has_stroke = any(kw in disease_name for kw in stroke_kw)

    # 也检查 DDx 中是否有卒中
    if not has_stroke:
        ddx = state.get("ddx_list", []) or []
        has_stroke = any(
            any(kw in (d.get("diagnosis", "") or "").lower() for kw in stroke_kw)
            for d in ddx
        )

    if not has_stroke:
        return {"document_chain": chain + ["stroke_at_check"]}

    meds = state.get("medication_adjustments", []) or []
    handoff = state.get("handoff_items", []) or []

    # 抗栓药关键词
    antithrombotic_kw = [
        "阿司匹林", "aspirin", "氯吡格雷", "clopidogrel", "替格瑞洛", "ticagrelor",
        "华法林", "warfarin", "利伐沙班", "rivaroxaban", "阿哌沙班", "apixaban",
        "达比加群", "dabigatran", "双嘧达莫", "dipyridamole",
        "抗血小板", "antiplatelet", "抗凝", "anticoagulant",
    ]

    has_at = False
    # 检查用药列表
    for m in meds:
        if not isinstance(m, dict):
            continue
        drug = str(m.get("drug") or m.get("medication") or "").lower()
        if any(kw.lower() in drug for kw in antithrombotic_kw):
            has_at = True
            break

    # 检查 handoff 中是否提到抗栓
    if not has_at:
        for h in handoff:
            content = str(h.get("content", "") or "").lower()
            if any(kw.lower() in content for kw in antithrombotic_kw):
                has_at = True
                break

    alerts = list(state.get("clinical_alerts", []) or [])

    if has_at:
        logger.info("node_stroke_antithrombotic: patient=%s stroke antithrombotic OK", patient_id)
    else:
        alert = "[STK-2] 卒中出院抗栓缺失: 缺血性卒中患者出院时应处方抗血小板/抗凝药, 除非有禁忌"
        alerts.append(alert)
        logger.info("node_stroke_antithrombotic: patient=%s antithrombotic MISSING", patient_id)

    return {
        "document_chain": chain + ["stroke_at_check"],
        "clinical_alerts": alerts,
    }


# ── A4: MDT 多学科会诊触发 ──


async def node_mdt_trigger(state: dict) -> dict:
    """MDT 多学科会诊触发 — 临床告警数量达标时自动发起。

    模板 mdt_threshold: 触发阈值（告警数量）
    模板 mdt_roles: 需要的专科列表
    仅在 monitoring 阶段执行，每天最多触发一次。
    """
    patient_id = state.get("patient_id", "unknown")
    chain = state.get("document_chain", [])

    # 幂等：每天最多一次
    if "mdt_triggered" in chain:
        return {}
    if state.get("phase") != "monitoring":
        return {}

    tpl = state.get("disease_template", {}) or {}
    mdt_threshold_raw = tpl.get("mdt_threshold")
    mdt_roles = tpl.get("mdt_roles", []) or []

    # 未配置 MDT 则跳过
    if not mdt_threshold_raw or not mdt_roles:
        return {}

    # 阈值可能是字符串（来自 YAML 模板），统一转 int
    try:
        mdt_threshold = int(mdt_threshold_raw)
    except (ValueError, TypeError):
        return {}

    alerts = state.get("clinical_alerts", []) or []
    alert_count = len(alerts)

    if alert_count < mdt_threshold:
        return {}

    # 达标 → 发起会诊
    roles_str = "、".join(mdt_roles) if isinstance(mdt_roles, list) else str(mdt_roles)
    alert = f"[MDT] 多学科会诊触发: 临床告警 {alert_count} 条 ≥ 阈值 {mdt_threshold}, 需 {roles_str} 联合会诊"

    logger.info("node_mdt_trigger: patient=%s MDT triggered (alerts=%d, threshold=%d)",
                patient_id, alert_count, mdt_threshold)

    record("mdt_trigger")
    new_alerts = list(alerts) + [alert]
    from .workflow_briefs import build_workflow_brief

    brief = await build_workflow_brief({**state, "clinical_alerts": new_alerts}, "mdt")

    return {
        "clinical_alerts": new_alerts,
        "workflow_briefs": {**(state.get("workflow_briefs") or {}), "mdt": brief},
        "clinical_evidence": _merge_evidence_citations(state, brief.get("citations") or []),
        "document_chain": chain + ["mdt_triggered"],
    }


# ── A6: Padua VTE 风险评分 ──


def _calc_padua(state: dict) -> tuple:
    """计算 Padua 评分。返回 (总分, 风险因子列表)。"""
    score = 0
    factors = []

    tpl = state.get("disease_template", {}) or {}
    p_data = state.get("patient_data", {}) or {}
    p_hist = state.get("patient_history", {}) or {}
    ddx = state.get("ddx_list", []) or []
    alerts = state.get("clinical_alerts", []) or []

    disease_id = (tpl.get("disease_id") or tpl.get("name", "")).lower()

    # 1. 活动性肿瘤 (3分)
    tumor_kw = ["tumor", "chemo", "cancer", "肿瘤", "化疗", "癌", "malignancy"]
    if any(kw in disease_id for kw in tumor_kw):
        score += 3
        factors.append("活动性肿瘤(+3)")

    # 2. 既往 VTE (3分) — 从 DDx 或 history 判断
    vte_kw = ["VTE", "DVT", "深静脉血栓", "肺栓塞", "PE", "venous thromboembolism"]
    has_vte_history = any(
        any(kw.lower() in (d.get("diagnosis", "") or "").lower() for kw in vte_kw)
        for d in ddx
    )
    # 也检查 patient_history
    pmh = p_hist.get("pmh") or p_hist.get("comorbidities") or {}
    pmh_str = str(pmh).lower()
    if any(kw.lower() in pmh_str for kw in vte_kw):
        has_vte_history = True
    if has_vte_history:
        score += 3
        factors.append("既往VTE(+3)")

    # 3. 活动受限 (3分) — post_surgery、stroke、卧床
    immobile_kw = ["surgery", "术后", "stroke", "卒中", "卧床", "immobile", "bedridden"]
    if any(kw in disease_id for kw in immobile_kw):
        score += 3
        factors.append("活动受限(+3)")

    # 4. 已知血栓形成倾向 (3分)
    thrombo_kw = ["thrombophilia", "血栓", "抗磷脂", "antiphospholipid", "factor V"]
    if any(kw.lower() in pmh_str for kw in thrombo_kw):
        score += 3
        factors.append("血栓形成倾向(+3)")

    # 5. 近期创伤/手术 (2分)
    if any(kw in disease_id for kw in ["surgery", "术后", "trauma", "创伤"]):
        score += 2
        factors.append("近期创伤/手术(+2)")

    # 6. 高龄 ≥70岁 (1分)
    age = p_hist.get("age") or p_data.get("age")
    try:
        if age is not None and int(age) >= 70:
            score += 1
            factors.append("高龄≥70(+1)")
    except (ValueError, TypeError):
        pass

    # 7. 心衰/呼衰 (1分)
    hf_rf_kw = ["heart failure", "心衰", "respiratory failure", "呼衰", "HF", "COPD"]
    if any(kw in disease_id for kw in hf_rf_kw):
        score += 1
        factors.append("心衰/呼衰(+1)")

    # 8. 急性心梗/卒中 (1分)
    ami_stroke_kw = ["cad", "acs", "心梗", "mi", "stroke", "卒中", "梗死"]
    if any(kw in disease_id for kw in ami_stroke_kw):
        score += 1
        factors.append("急性心梗/卒中(+1)")

    # 9. 急性感染/风湿 (1分)
    infection_kw = ["pneumonia", "肺炎", "infection", "感染", "sepsis"]
    if any(kw in disease_id for kw in infection_kw):
        score += 1
        factors.append("急性感染(+1)")

    # 10. 肥胖 BMI≥30 (1分)
    bmi = p_hist.get("bmi") or p_data.get("bmi")
    try:
        if bmi is not None and float(bmi) >= 30:
            score += 1
            factors.append("肥胖BMI≥30(+1)")
    except (ValueError, TypeError):
        pass

    # 11. 激素治疗 (1分) — 检查用药
    meds = state.get("medication_adjustments", []) or []
    hormone_kw = ["激素", "hormone", "steroid", "estrogen", "tamoxifen", "contraceptive"]
    for m in meds:
        if not isinstance(m, dict):
            continue
        drug = str(m.get("drug") or m.get("medication") or "").lower()
        if any(kw in drug for kw in hormone_kw):
            score += 1
            factors.append("激素治疗(+1)")
            break

    return score, factors


async def node_padua_score(state: dict) -> dict:
    """Padua VTE 风险评分 — 入院后评估 VTE 风险等级。

    ≥4 分高风险 → VTE-1 预防必须到位。
    仅在入院确认后执行一次。
    """
    patient_id = state.get("patient_id", "unknown")
    chain = state.get("document_chain", [])

    if "padua_scored" in chain:
        return {}
    if "doctor_confirm_auto" not in chain and state.get("doctor_confirm_status") != "approved":
        return {}

    score, factors = _calc_padua(state)
    risk = "high" if score >= 4 else "low"

    logger.info("node_padua_score: patient=%s Padua=%d (%s), factors=%s",
                patient_id, score, risk, factors)

    record("padua")

    alerts = list(state.get("clinical_alerts", []) or [])
    result = {
        "padua_score": score,
        "padua_risk": risk,
        "document_chain": chain + ["padua_scored"],
    }

    if score >= 4:
        factor_str = "; ".join(factors)
        alert = f"[Padua={score}] VTE高风险: {factor_str} → 建议低分子肝素或磺达肝癸钠预防"
        alerts.append(alert)
        result["clinical_alerts"] = alerts

    return result
