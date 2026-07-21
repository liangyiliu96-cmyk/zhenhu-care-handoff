"""Agent 节点 —— 监测、查房、用药调整、检验审阅、转科。

包含: node_monitoring, node_daily_round, node_medication_adjust,
node_lab_review, node_transfer, _analyze_vs_trend。
"""

import json
import logging
from datetime import datetime

from .nodes_admission import _check_discharge_criteria
from .llm_utils import deep_invoke, safe_llm_invoke  # P1-4
from .metrics import record
from .llm_utils import get_provider_for_node  # P1-2
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


def _check_complication_watch(state: dict, vs: list) -> list[str]:
    """对照 complication_monitoring 的 watch 条件，检查当前体征和检验是否触发。

    返回应追加到 clinical_alerts 的告警列表。
    """
    template = state.get("disease_template") or {}
    complications = template.get("complication_monitoring") or []
    if not complications or not vs:
        return []

    latest = vs[-1]
    labs = state.get("lab_results") or []
    lab_map = {l.get("name", ""): l.get("value") for l in labs if l.get("name")}

    alerts = []
    for comp in complications:
        name = comp.get("complication", "未知并发症")
        watches = comp.get("watch", [])
        triggered = []
        for w in watches:
            if _match_watch(w, latest, lab_map):
                triggered.append(w)
        if triggered:
            alerts.append(f"[并发症] {name} 预警: {'; '.join(triggered[:3])}")

    return alerts


def _match_watch(watch: str, vs: dict, lab_map: dict) -> bool:
    """匹配单条 watch 条件。

    支持格式:
    - "体温>38℃" → temperature > 38
    - "SpO2<92%" → spo2 < 92
    - "心率>110" → heart_rate > 110
    - "D-二聚体升高" → key check
    - "WBC升高" → fuzzy match
    """
    import re

    # 量化条件: "体征名>值" 或 "体征名<值"
    # 支持中英文/数字体征名 (如 SpO2, 体温, MAP, GCS)
    m = re.match(r'([A-Za-z\d\u4e00-\u9fff]+)\s*([><])\s*([\d.]+)', watch)
    if m:
        key_raw = m.group(1).strip()
        op = m.group(2)
        threshold = float(m.group(3))

        # 映射体征名
        key_map = {
            "体温": "temperature", "temperature": "temperature",
            "SpO2": "spo2", "spo2": "spo2", "SpO": "spo2",
            "心率": "heart_rate", "HR": "heart_rate", "heart_rate": "heart_rate",
            "呼吸": "respiratory_rate", "RR": "respiratory_rate", "respiratory_rate": "respiratory_rate",
            "收缩压": "systolic_mmhg", "SBP": "systolic_mmhg",
            "舒张压": "diastolic_mmhg", "DBP": "diastolic_mmhg",
            "血糖": "blood_glucose", "blood_glucose": "blood_glucose",
            "MAP": "systolic_mmhg",  # MAP ≈ 舒张压 + 1/3脉压差可用SBP近似
            "GCS": "gcs", "gcs": "gcs",
        }
        mapped_key = key_map.get(key_raw, key_raw.lower().replace(" ", "_"))
        val = vs.get(mapped_key)
        if val is None:
            val = lab_map.get(key_raw)
        if val is not None:
            try:
                fval = float(val)
                if op == ">" and fval > threshold:
                    return True
                if op == "<" and fval < threshold:
                    return True
            except (ValueError, TypeError):
                pass

    # 检验项模糊匹配 (仅此路径可行——lab_map 值可为 None)
    for lab_name, lab_val in lab_map.items():
        if lab_name in watch and lab_val is not None:
            return True

    # 非量化文本条件永不命中: 体征值全为数值, watch 条件如"广泛出血倾向"无法匹配
    return False


async def node_monitoring(state: dict) -> dict:
    """持续监测: 逐条检查 discharge_criteria，全部满足才批准出院。

    P0-1修复: 不再按体征数量批准出院。
    """
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_monitoring: start, patient=%s", patient_id)
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    risk = state.get("risk_level", "low")

    criteria = template.get("discharge_criteria", [])
    criteria_result = await _check_discharge_criteria(criteria, vs, state)

    result = {
        "phase": "monitoring",
        "monitoring_strategy": f"risk_{risk}",
        "discharge_criteria_check": criteria_result,
    }

    if criteria_result.get("all_met", False):
        result["discharge_decision"] = "approved"

    # ##3 BMI 自动计算
    latest = vs[-1] if vs else {}
    weight = latest.get("weight_kg") or state.get("weight_kg")
    height = latest.get("height_cm") or state.get("height_cm")
    if weight and height:
        try:
            height_m = float(height) / 100
            bmi = round(float(weight) / (height_m * height_m), 1)
            result["weight_kg"] = float(weight)
            result["height_cm"] = float(height)
            result["bmi"] = bmi
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # 并发症主动监测: 对照 complication_monitoring 的 watch 条件检查体征/检验
    complication_alerts = _check_complication_watch(state, vs)
    if complication_alerts:
        existing_alerts = list(state.get("clinical_alerts", []) or [])
        result["clinical_alerts"] = existing_alerts + complication_alerts

    record("monitoring")
    return result


async def node_daily_round(state: dict) -> dict:
    """SOAP格式查房模板。P0修复: fallback引用已有临床数据，prompt丰富化(HPI/PE/DDx)。"""
    current_input_counts = {
        "vitals": len(state.get("vital_signs", []) or []),
        "labs": len(state.get("lab_results", []) or []),
        "medications": len(state.get("medication_adjustments", []) or []),
    }
    if state.get("last_round_input_counts") == current_input_counts:
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_daily_round: start, patient=%s", patient_id)
    vs = state.get("vital_signs", [])
    labs = state.get("lab_results", [])
    meds = state.get("medication_adjustments", [])
    chain = state.get("document_chain", [])
    risk = state.get("risk_level", "low")
    template = state.get("disease_template", {})
    round_number = int(state.get("round_count", 0)) + 1

    # 从上游节点取新临床数据
    hpi = state.get("hpi_narrative") or ""
    pe = state.get("pe_narrative") or ""
    history_data = state.get("history_data") or {}
    ddx = state.get("ddx_list") or []
    chief_complaint = history_data.get("chief_complaint", "")

    # 生命体征趋势
    latest_vs = vs[-1] if vs else {}
    vs_trend = _analyze_vs_trend(vs[-4:]) if len(vs) >= 4 else "数据不足"

    # SOAP 主观+评估+计划 —— 用已有临床数据做 fallback（不再写"未接入LLM"）
    subjective = {
        "chief_complaint": chief_complaint or "待补充",
        "symptoms_since_last_round": "体征趋势: " + vs_trend,
    }
    assessment = {
        "stability": "stable" if vs_trend == "稳定" else "unstable",
        "response_to_treatment": f"体征趋势{vs_trend}，已调药{len(meds)}次" if meds else "未调整用药",
        "key_findings": (hpi[:100] + "..." if len(hpi) > 100 else hpi) or "病史待采集",
    }
    plan = {
        "continue_monitoring": risk != "high",
        "consider_discharge": len(vs) >= 6 and risk != "high",
        "next_labs": "按病种模板复查",
    }

    # ── H6: 查房 prompt 补充最近检验 ──
    recent_labs = labs[-3:] if labs else []
    recent_labs_str = ""
    if recent_labs:
        recent_labs_str = f"\n最近检验结果: {json.dumps(recent_labs, ensure_ascii=False)}"

    generation_source = "rule_based"

    # LLM增强: 用新临床数据丰富 prompt
    try:
        provider = get_provider_for_node("daily_round")
        llm_prompt = prompts.daily_round_prompt(
            template.get('name', '未知'), risk, chief_complaint,
            hpi, pe, ddx, latest_vs,
            vs_trend, len(labs), len(meds),
            recent_labs_str, template.get('complication_monitoring', [])
        )
        llm_context = {
            "disease_template": template,
            "vital_signs_latest": latest_vs,
            "risk_level": risk,
            "hpi": hpi[:200],
            "pe": pe[:200],
        }
        llm_result = await safe_llm_invoke(provider, llm_prompt, context=llm_context, caller="monitoring", timeout=10.0)

        if llm_result and llm_result.get("source_type") != "source_none":
            generation_source = "llm_assisted"
            subjective["chief_complaint"] = llm_result.get("chief_complaint", subjective["chief_complaint"])
            subjective["symptoms_since_last_round"] = llm_result.get(
                "symptoms_since_last_round", subjective["symptoms_since_last_round"]
            )
            assessment["response_to_treatment"] = llm_result.get(
                "response_to_treatment", assessment["response_to_treatment"]
            )
            plan["next_labs"] = llm_result.get("next_labs", plan["next_labs"])
    except Exception:
        logger.warning("node_daily_round: LLM failed, patient=%s", patient_id)

    round_note = {
        "type": "daily_round",
        "format": "SOAP",
        "subjective": subjective,
        "objective": {
            "vital_signs_latest": latest_vs,
            "vital_signs_trend": vs_trend,
            "lab_count": len(labs),
            "med_adjust_count": len(meds),
            "risk_level": risk,
        },
        "assessment": assessment,
        "plan": plan,
        "round_number": round_number,
        "timestamp": datetime.now().isoformat(),
    }

    record("daily_round")

    # 方案1 临床决策推送: DeepAgent 管线 (Collect→Execute)
    ai_recommendation = ""
    evidence_citations = []
    try:
        provider = get_provider_for_node("daily_round")
        from .llm_utils import deep_invoke
        meds = state.get("medication_adjustments", []) or []
        discharge_check = state.get("discharge_criteria_check", {}) or {}
        all_met = discharge_check.get("all_met", False)
        vs_text = json.dumps(latest_vs, ensure_ascii=False) if latest_vs else "无"
        rec_prompt = (
            f"基于以下临床上下文，用一句中文（30字内）给出最优先的临床行动建议：\n"
            f"病种: {template.get('name', template.get('disease_id', ''))}，"
            f"NEWS2={state.get('news2_score', '?')}，风险={risk}\n"
            f"最新体征: {vs_text}\n"
            f"用药调整数: {len(meds)}，最近调整: {json.dumps(meds[-1] if meds else {}, ensure_ascii=False)[:100]}\n"
            f"出院标准: {'全部达标' if all_met else '未达标'}，"
            f"告警: {len(state.get('clinical_alerts', []) or [])}条\n"
            f"仅返回一句中文建议，不要解释。"
        )
        disease_name = template.get("name") or template.get("disease_id", "")
        llm_result = await deep_invoke(
            provider, rec_prompt,
            rag_query=f"{disease_name} NEWS2={state.get('news2_score','?')} 风险={risk} 临床处理",
            caller="daily_round", timeout=10.0,
        )
        ai_recommendation = (llm_result or {}).get("response", "") if llm_result else ""
        evidence_citations = list((llm_result or {}).get("_rag_citations", []) or [])
        if ai_recommendation:
            generation_source = "llm_assisted"
        if not ai_recommendation:
            # 规则fallback: 避免空白
            if all_met:
                ai_recommendation = "出院标准已全部达标，可择期出院。"
            elif risk == "high":
                ai_recommendation = "患者高危，建议加强监测频率。"
            else:
                ai_recommendation = "体征稳定，继续当前治疗方案。"
    except Exception:
        ai_recommendation = "继续当前治疗方案。"

    existing_evidence = list(state.get("clinical_evidence", []) or [])
    existing_ids = {item.get("citation_id") for item in existing_evidence if isinstance(item, dict)}
    for citation in evidence_citations:
        if isinstance(citation, dict) and citation.get("citation_id") not in existing_ids:
            existing_evidence.append(citation)
            existing_ids.add(citation["citation_id"])

    round_note.update({
        "generation_source": generation_source,
        "review_status": "requires_clinician_review",
        "ai_recommendation": ai_recommendation,
        "citations": evidence_citations,
        "source_nodes": ["vital_signs", "lab_results", "medication_adjustments", "daily_round_agent"],
    })

    return {
        "phase": "daily_round",
        "document_chain": chain + ["daily_round_note"],
        "latest_round": round_note,
        "round_count": round_number,
        "round_history": [*(state.get("round_history") or []), round_note],
        "last_round_input_counts": current_input_counts,
        "ai_recommendation": ai_recommendation,
        "clinical_evidence": existing_evidence[-20:],
    }


def _analyze_vs_trend(vital_signs: list[dict]) -> str:
    """分析生命体征趋势。"""
    if len(vital_signs) < 2:
        return "数据不足"
    # 简化: 检查最近和最远
    latest = vital_signs[-1]
    earliest = vital_signs[0]
    # 只比较数值型字段
    stable = True
    for key in ["heart_rate", "spo2", "temperature"]:
        lv = latest.get(key)
        ev = earliest.get(key)
        if isinstance(lv, (int, float)) and isinstance(ev, (int, float)):
            if abs(lv - ev) / max(abs(ev), 1) > 0.15:
                stable = False
                break
    return "稳定" if stable else "波动中"


async def node_medication_adjust(state: dict) -> dict:
    """用药调整: 连续≥2次体征异常才触发，必须医生确认。
    
    P0-2修复: 单次异常不触发调药，需连续异常+医生确认标识。
    """
    if state.get("medication_adjustments"):
        return {}

    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    alert_history = state.get("consecutive_abnormal_count", 0)
    alerts = []
    
    # 建立阈值查找表 {name: (alert_above_f, alert_below_f)}
    # P0-2: 类型安全转换，防止字符串阈值触发 TypeError
    thresholds = {}
    for v_def in template.get("vital_signs", []):
        name = v_def.get("name", "")
        if name:
            def _safe_float(v):
                if v is None:
                    return None
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, str):
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None
                return None
            thresholds[name] = (_safe_float(v_def.get("alert_above")), _safe_float(v_def.get("alert_below")))

    # 单次扫描最近2条体征
    recent = vs[-2:] if len(vs) >= 2 else vs
    for v in recent:
        for key, val in v.items():
            if key not in thresholds or not isinstance(val, (int, float)):
                continue
            alert_above, alert_below = thresholds[key]
            val_f = float(val)
            if (alert_above is not None and val_f > alert_above) or \
               (alert_below is not None and val_f < alert_below):
                alert_history += 1
                alerts.append({"sign": key, "consecutive_count": alert_history})
                break  # 每个体征记录只记一次告警
        else:
            continue
        break  # 已触发告警
    else:
        alert_history = 0  # 最近2条均无异常
    
    adjustments = state.get("medication_adjustments", [])
    evidence_citations = []
    if alerts and alert_history >= 2:
        # LLM生成调药建议
        suggestion = "建议医生评估调药(连续异常)"
        urgency = "routine"
        try:
            provider = get_provider_for_node("medication_adjust")
            llm_result = await deep_invoke(
                provider,
                f"基于以下体征异常生成用药调整建议（1-2句中文，含具体药物类别建议）："
                f"病种: {template.get('name', '未知')}。"
                f"异常体征: {json.dumps(alerts, ensure_ascii=False)}。"
                f"用药方案: {json.dumps(template.get('medication_protocol',{}), ensure_ascii=False)}\n"
                f"禁忌: {json.dumps(template.get('contraindications',[]), ensure_ascii=False)}\n"
                f"返回JSON: {{\"suggestion\": \"...\", \"urgency\": \"routine/urgent/emergent\"}}",
                context={"disease_template": template, "alerts": alerts},
                rag_query=f"{template.get('name', '')} medication adjustment vital sign abnormality",
                caller="medication_adjust",
                timeout=10.0,
            )
            if llm_result and llm_result.get("source_type") != "source_none":
                suggestion = llm_result.get("suggestion", suggestion)
                urgency = llm_result.get("urgency", "routine")
                evidence_citations = list(llm_result.get("_rag_citations", []) or [])
        except Exception:
            urgency = "routine"

        adjustments.append({
            "reason": alerts,
            "action": suggestion,
            "timestamp": datetime.now().isoformat(),
            "requires_doctor_confirm": True,
            "urgency": urgency,
        })
    
    record("medication_adjust")
    return {
        "phase": "medication_adjust",
        "medication_alerts": alerts,
        "medication_adjustments": adjustments,
        "consecutive_abnormal_count": alert_history,
        "clinical_evidence": _merge_evidence_citations(state, evidence_citations),
    }


async def node_lab_review(state: dict) -> dict:
    """检查结果审阅——LLM解读异常检验结果。"""
    labs = state.get("lab_results", [])
    reviewed = state.get("reviewed_labs", [])
    template = state.get("disease_template", {})
    reviewed_count = state.get("reviewed_lab_count")
    if reviewed_count is None:
        reviewed_count = len(reviewed)
    reviewed_count = max(0, min(int(reviewed_count), len(labs)))
    new_labs = labs[reviewed_count:]
    if not new_labs:
        return {}
    findings = []
    evidence_citations = []
    
    for lab in new_labs:
        finding = {
            "test": lab.get("name", "unknown"),
            "result": lab.get("value", "N/A"),
            "unit": lab.get("unit", ""),
            "status": "reviewed",
        }
        findings.append(finding)
    
    # LLM 临床解读：有异常结果时生成临床判断
    if new_labs:
        provider = get_provider_for_node("lab_review")
        llm_prompt = prompts.lab_review_prompt(
            template.get('name', '未知'), new_labs
        )
        llm_ctx = {"disease_template": template, "lab_results": new_labs}
        llm_result = await deep_invoke(
            provider,
            llm_prompt,
            context=llm_ctx,
            rag_query=f"{template.get('name', '')} lab review {new_labs[0].get('name', '')}",
            caller="lab_review",
            timeout=10.0,
        )
        if llm_result and llm_result.get("source_type") != "source_none":
            for finding in findings:
                finding["interpretation"] = llm_result.get("interpretation", "")
                finding["recommendation"] = llm_result.get("recommendation", "")
            evidence_citations = list(llm_result.get("_rag_citations", []) or [])

    record("lab_review")

    # ── abnormal_lab alerts → clinical_alerts ──
    lab_refs = template.get("lab_reference", {}) or {}
    abnormal_alerts = []
    for lab in new_labs:
        name = lab.get("name", "")
        value = lab.get("value")
        unit = lab.get("unit", "")
        ref = lab_refs.get(name, {})
        if ref and value is not None:
            lo = ref.get("low")
            hi = ref.get("high")
            try:
                v = float(value)
                if (lo is not None and v < lo) or (hi is not None and v > hi):
                    abnormal_alerts.append(f"[异常检验] {name}={value}{unit} (参考 {lo}-{hi}{unit})")
            except (ValueError, TypeError):
                pass

    return {
        "phase": "lab_review",
        "reviewed_labs": reviewed + new_labs,
        "reviewed_lab_count": len(labs),
        "lab_findings": findings,
        "document_chain": state.get("document_chain", []) + (["lab_review"] if new_labs else []),
        "clinical_alerts": (state.get("clinical_alerts") or []) + abnormal_alerts,
        "clinical_evidence": _merge_evidence_citations(state, evidence_citations),
    }


async def node_transfer(state: dict) -> dict:
    """P1修复: 增加疾病特异性转科标准，替代仅靠高危+体征计数。"""
    if "transfer_assessment" in state.get("document_chain", []):
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_transfer: start, patient=%s", patient_id)
    risk_level = state.get("risk_level", "low")
    vs = state.get("vital_signs", [])
    template = state.get("disease_template", {})
    disease_id = template.get("disease_id", "")

    transfer_needed = False
    transfer_target = None
    transfer_reason = None
    evidence_citations = []

    # 休克征象(通用): SBP<90 或 HR>120 + SBP<100
    for v in vs[-3:]:
        sbp = v.get("blood_pressure_systolic", v.get("systolic_mmhg", 0))
        bp_str = v.get("blood_pressure", "")
        if isinstance(bp_str, str) and "/" in bp_str:
            parts = bp_str.split("/")
            sbp = int(parts[0]) if parts[0].isdigit() else sbp
        hr = v.get("heart_rate", 0)
        if isinstance(sbp, (int, float)) and isinstance(hr, (int, float)):
            if sbp < 90 or (hr > 120 and sbp < 100):
                transfer_needed = True
                transfer_target = "ICU"
                transfer_reason = "血流动力学不稳定(休克征象)"
                break

    # 呼吸衰竭: SpO2<90%(吸氧下) 或 呼吸频率>35
    if not transfer_needed:
        for v in vs[-3:]:
            spo2 = v.get("spo2", 100)
            rr = v.get("respiratory_rate", 16)
            if isinstance(spo2, (int, float)) and isinstance(rr, (int, float)):
                if spo2 < 90 or rr > 35:
                    transfer_needed = True
                    transfer_target = "ICU"
                    transfer_reason = "呼吸衰竭征象"
                    break

    # 意识障碍: GCS<9
    if not transfer_needed:
        for v in vs[-3:]:
            gcs = v.get("gcs", 15)
            if isinstance(gcs, (int, float)) and gcs < 9:
                transfer_needed = True
                transfer_target = "ICU"
                transfer_reason = f"意识障碍(GCS={gcs})"
                break

    # 疾病特异性转科
    disease_transfer_map = {
        "stroke": ("神经外科", "NIHSS恶化或大面积脑梗死"),
        "heart_failure": ("CCU", "心源性休克或急性肺水肿"),
        "gi_bleeding": ("ICU", "活动性出血伴血流动力学不稳定"),
        "aki": ("肾内科ICU", "需要紧急肾脏替代治疗"),
    }

    if not transfer_needed and disease_id in disease_transfer_map:
        target, reason_base = disease_transfer_map[disease_id]
        # 仅高危+已尝试调药才触发疾病特异性转科
        if risk_level == "high" and state.get("medication_adjustments"):
            transfer_needed = True
            transfer_target = target
            transfer_reason = reason_base

    # LLM增强: 转科理由
    if transfer_needed:
        provider = get_provider_for_node("transfer")
        llm_result = await deep_invoke(
            provider,
            f"生成转科至{transfer_target}的简要临床理由（1句中文）："
            f"转科原因: {transfer_reason}，病种: {template.get('disease_id', '')}。"
            f"返回JSON: {{\"rationale\": \"...\"}}",
            context={"transfer_reason": transfer_reason, "transfer_target": transfer_target},
            rag_query=f"{template.get('disease_id', '')} transfer {transfer_target} {transfer_reason}",
            caller="transfer",
            timeout=10.0,
        )
        if llm_result and llm_result.get("source_type") != "source_none":
            transfer_reason = f"{transfer_reason}。{llm_result.get('rationale', '')}"
            evidence_citations = list(llm_result.get("_rag_citations", []) or [])

    # G4: 未匹配到具体科室/原因时使用默认值（Command 端点可覆盖已存在的值）
    if transfer_needed:
        if not transfer_target:
            transfer_target = "ICU"
        if not transfer_reason:
            transfer_reason = "高危体征持续异常"

    record("transfer")
    result = {
        "phase": "transfer",
        "transfer_needed": transfer_needed,
        "transfer_target": transfer_target,
        "transfer_reason": transfer_reason,
        "document_chain": state.get("document_chain", []) + ["transfer_assessment"],
        "clinical_evidence": _merge_evidence_citations(state, evidence_citations),
    }
    if transfer_needed:
        from .workflow_briefs import build_workflow_brief

        brief = await build_workflow_brief({**state, **result}, "transfer")
        result["workflow_briefs"] = {**(state.get("workflow_briefs") or {}), "transfer": brief}
        result["clinical_evidence"] = _merge_evidence_citations(result, brief.get("citations") or [])
    return result
