"""Agent 节点 —— 监测、查房、用药调整、检验审阅、转科。

包含: node_monitoring, node_daily_round, node_medication_adjust,
node_lab_review, node_transfer, _analyze_vs_trend。
"""

import json
import logging
from datetime import datetime

from .nodes_admission import _check_discharge_criteria
from zhenhu.contracts.agent import get_ai_provider

logger = logging.getLogger("zhenhu.inpatient")


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
    criteria_result = _check_discharge_criteria(criteria, vs, state)
    
    result = {
        "phase": "monitoring",
        "monitoring_strategy": f"risk_{risk}",
        "discharge_criteria_check": criteria_result,
    }
    
    if criteria_result.get("all_met", False):
        result["discharge_decision"] = "approved"
    
    return result


async def node_daily_round(state: dict) -> dict:
    """P1修复: SOAP格式查房模板。Phase5: LLM生成真实临床内容（含回退）。"""
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_daily_round: start, patient=%s", patient_id)
    vs = state.get("vital_signs", [])
    labs = state.get("lab_results", [])
    meds = state.get("medication_adjustments", [])
    chain = state.get("document_chain", [])
    risk = state.get("risk_level", "low")
    template = state.get("disease_template", {})

    # 生命体征趋势
    latest_vs = vs[-1] if vs else {}
    vs_trend = _analyze_vs_trend(vs[-4:]) if len(vs) >= 4 else "数据不足"

    # SOAP 主观+评估+计划 —— 尝试LLM生成
    subjective = {"chief_complaint": "患者自述(未接入LLM)", "symptoms_since_last_round": "自觉症状变化(未接入LLM)"}
    assessment = {"stability": "stable" if vs_trend == "稳定" else "unstable", "response_to_treatment": "评估中(未接入LLM)"}
    plan = {"continue_monitoring": risk != "high", "consider_discharge": len(vs) >= 6 and risk != "high", "next_labs": "按病种模板复查(未接入LLM)"}

    try:
        provider = get_ai_provider()
        llm_prompt = (
            f"根据以下住院患者数据生成SOAP格式查房笔记的 subjective/assessment/plan 部分。"
            f"病种: {template.get('name', '未知')}, 风险等级: {risk}。"
            f"最新体征: {json.dumps(latest_vs, ensure_ascii=False)}。"
            f"体征趋势: {vs_trend}。化验数: {len(labs)}, 用药调整数: {len(meds)}。"
        )
        llm_context = {"disease_template": template, "vital_signs_latest": latest_vs, "risk_level": risk}
        llm_result = await provider.invoke(llm_prompt, context=llm_context)

        if llm_result and llm_result.get("source_type") != "source_none":
            subjective["chief_complaint"] = llm_result.get("chief_complaint", subjective["chief_complaint"])
            subjective["symptoms_since_last_round"] = llm_result.get("symptoms_since_last_round", subjective["symptoms_since_last_round"])
            assessment["response_to_treatment"] = llm_result.get("response_to_treatment", assessment["response_to_treatment"])
            plan["next_labs"] = llm_result.get("next_labs", plan["next_labs"])
    except Exception:
        logger.warning("node_daily_round: LLM failed, patient=%s", state.get("patient_id", "unknown"))
        pass  # LLM失败→使用默认占位，不阻断临床流程

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
        "timestamp": "daily-round-mock",
    }

    return {
        "phase": "daily_round",
        "document_chain": chain + ["daily_round_note"],
        "latest_round": round_note,
        "round_count": state.get("round_count", 0) + 1,
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
    template = state.get("disease_template", {})
    vs = state.get("vital_signs", [])
    alert_history = state.get("consecutive_abnormal_count", 0)
    alerts = []
    
    for v_def in template.get("vital_signs", []):
        name = v_def.get("name", "")
        alert_above = v_def.get("alert_above")
        alert_below = v_def.get("alert_below")
        
        if not name:
            continue
        
        # 只检查最近2条记录
        recent = vs[-2:] if len(vs) >= 2 else vs
        triggered = False
        for v in recent:
            val = v.get(name, 0)
            if not isinstance(val, (int, float)):
                continue
            if alert_above is not None and val > alert_above:
                triggered = True
                break
            if alert_below is not None and val < alert_below:
                triggered = True
                break
        
        if triggered:
            alert_history += 1
            alerts.append({"sign": name, "consecutive_count": alert_history})
        else:
            alert_history = 0
    
    adjustments = state.get("medication_adjustments", [])
    if alerts and alert_history >= 2:
        adjustments.append({
            "reason": alerts,
            "action": "建议医生评估调药(连续异常)",
            "timestamp": datetime.now().isoformat(),
            "requires_doctor_confirm": True,
        })
    
    return {
        "phase": "medication_adjust",
        "medication_alerts": alerts,
        "medication_adjustments": adjustments,
        "consecutive_abnormal_count": alert_history,
    }


async def node_lab_review(state: dict) -> dict:
    """检查结果审阅——LLM解读异常检验结果。"""
    labs = state.get("lab_results", [])
    reviewed = state.get("reviewed_labs", [])
    template = state.get("disease_template", {})
    
    new_labs = [lab for lab in labs if lab not in reviewed]
    findings = []
    
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
        try:
            provider = get_ai_provider()
            llm_prompt = (
                f"根据病种'{template.get('name', '未知')}'的背景，审阅以下检验结果并给出临床判断。"
                f"检验: {json.dumps([{'test': l.get('name',''), 'value': l.get('value',''), 'unit': l.get('unit','')} for l in new_labs], ensure_ascii=False)}。"
                f"返回JSON: {{\"interpretation\": \"异常结果综合解读(1-2句)\", \"abnormal_findings\": [...], \"recommendation\": \"下一步建议\"}}"
            )
            llm_ctx = {"disease_template": template, "lab_results": new_labs}
            llm_result = await provider.invoke(llm_prompt, context=llm_ctx)
            if llm_result and llm_result.get("source_type") != "source_none":
                for finding in findings:
                    finding["interpretation"] = llm_result.get("interpretation", "")
                    finding["recommendation"] = llm_result.get("recommendation", "")
        except Exception:
            pass  # LLM失败→仅标记reviewed，不阻断
    
    return {
        "phase": "lab_review",
        "reviewed_labs": reviewed + new_labs,
        "lab_findings": findings,
        "document_chain": state.get("document_chain", []) + (["lab_review"] if new_labs else []),
    }


async def node_transfer(state: dict) -> dict:
    """P1修复: 增加疾病特异性转科标准，替代仅靠高危+体征计数。"""
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_transfer: start, patient=%s", patient_id)
    risk_level = state.get("risk_level", "low")
    vs = state.get("vital_signs", [])
    template = state.get("disease_template", {})
    disease_id = template.get("disease_id", "")

    transfer_needed = False
    transfer_target = None
    transfer_reason = None

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

    return {
        "phase": "transfer",
        "transfer_needed": transfer_needed,
        "transfer_target": transfer_target,
        "transfer_reason": transfer_reason,
    }
