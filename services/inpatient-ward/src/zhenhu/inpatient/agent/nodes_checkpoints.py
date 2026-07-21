"""Agent 医生审核卡点节点 —— P1-4 从 nodes_clinical.py 独立。

包含: _get_abnormal_labs（异常检验提取）、
node_doctor_confirm（卡点① 入院确认）、
node_doctor_med_confirm（卡点② 调药确认）、
node_doctor_discharge_sign（卡点③ 出院签字）。
全部节点均含幂等守卫，DOCTOR_AUTO_APPROVE=true 自动降级。
"""

import logging

from .config import is_doctor_auto_approve
from .metrics import record

logger = logging.getLogger("zhenhu.inpatient")


def _get_abnormal_labs(state: dict) -> list[dict]:
    """从 lab_results 和 disease_template 中提取异常检验结果。

    对比模板中的 reference_ranges，筛选超出范围的 lab 值。
    ##7: 根据患者年龄和性别校正参考范围。
    """
    labs = state.get("lab_results", []) or []
    template = state.get("disease_template", {}) or {}
    lab_reference = template.get("lab_reference", {}) or {}

    # ##7 年龄/性别校正
    p_data = state.get("patient_data") or {}
    age = p_data.get("age") or 0
    gender = (p_data.get("gender") or "").lower()
    is_female = gender in ("female", "女", "f")
    is_elderly = age >= 65

    lab_reference = dict(lab_reference)  # 拷贝，不修改模板原值
    for lab_name in list(lab_reference.keys()):
        ref = lab_reference[lab_name]
        # 肌酐: 女性/老年人降低上限
        if lab_name in ("肌酐", "Creatinine", "creatinine"):
            if is_female and is_elderly:
                lab_reference[lab_name] = {"low": ref.get("low", 44), "high": 88}
            elif is_female:
                lab_reference[lab_name] = {"low": ref.get("low", 44), "high": 97}
            elif is_elderly:
                lab_reference[lab_name] = {"low": ref.get("low", 44), "high": 104}
        # 血红蛋白: 女性下限更低
        elif lab_name in ("血红蛋白", "Hemoglobin", "Hb"):
            if is_female:
                lab_reference[lab_name] = {"low": 115, "high": ref.get("high", 150)}
        # 尿酸: 女性上限更低
        elif lab_name in ("尿酸", "Uric Acid", "uric_acid"):
            if is_female:
                lab_reference[lab_name] = {"low": ref.get("low", 150), "high": 357}

    abnormal = []
    for lab in labs:
        name = lab.get("name", "")
        value = lab.get("value")
        ref = lab_reference.get(name)
        if ref and value is not None:
            low = ref.get("low")
            high = ref.get("high")
            try:
                val = float(value)
                if (low is not None and val < low) or (high is not None and val > high):
                    abnormal.append({"name": name, "value": value,
                                    "unit": lab.get("unit", ""),
                                    "ref_range": f"{low}-{high}"})
            except (ValueError, TypeError):
                pass
    return abnormal


async def node_doctor_confirm(state: dict) -> dict:
    """卡点① 入院确认 — v1.3 §十一。

    幂等守卫：status in ("approved","rejected")。
    DOCTOR_AUTO_APPROVE=true 自动批准降级；
    否则挂起等待医生审核，写入 pending_review。
    """
    current_status = state.get("doctor_confirm_status")
    if current_status in ("approved", "rejected"):
        chain = state.get("document_chain", [])
        if "doctor_confirm_auto" not in chain:
            return {"document_chain": chain + ["doctor_confirm_auto"]}
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_doctor_confirm: start, patient=%s", patient_id)

    if is_doctor_auto_approve():
        record("doctor_confirm")
        return {
            "doctor_confirm_status": "approved",
            "document_chain": state.get("document_chain", []) + ["doctor_confirm_auto"],
        }

    review_id = f"rev-{patient_id}-confirm"
    history_data = state.get("history_data") or {}
    return {
        "pending_review": {
            "review_id": review_id,
            "type": "doctor_confirm",
            "payload": {
                "patient_id": patient_id,
                "risk_level": state.get("risk_level"),
                "triage_matched_factors": state.get("triage_matched_factors", []),
                "clinical_alerts": state.get("clinical_alerts", []),
                "history_summary": (history_data.get("hpi_narrative")
                                    or state.get("hpi_narrative") or "")[:200],
                "template": (state.get("disease_template", {})
                             .get("name",
                                  state.get("disease_template", {})
                                  .get("disease_id", ""))),
                "chief_complaint": (state.get("history_data") or {}).get("chief_complaint", ""),
                "hpi_narrative": state.get("hpi_narrative", ""),
                "pe_narrative": state.get("pe_narrative", ""),
                "ddx_list": state.get("ddx_list", []),
                "ddx_unavailable": state.get("ddx_unavailable", False),
                "allergies": state.get("allergies", []),
                "clinical_assessments": state.get("clinical_assessments", {}),
            },
        },
        "doctor_confirm_status": "pending",
        "interrupt_pending": True,
    }


async def node_doctor_med_confirm(state: dict) -> dict:
    """卡点② 调药确认 — v1.3 §十一。

    幂等守卫：status in ("approved","rejected")。
    DOCTOR_AUTO_APPROVE=true 自动批准降级；
    否则挂起等待医生审核调药方案。
    """
    current_status = state.get("med_confirm_status")
    if current_status in ("approved", "rejected"):
        chain = state.get("document_chain", [])
        if "med_reviewed" not in chain:
            return {"document_chain": chain + ["med_reviewed"]}
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_doctor_med_confirm: start, patient=%s", patient_id)

    if is_doctor_auto_approve():
        record("doctor_med_confirm")
        return {"med_confirm_status": "approved"}

    review_id = f"rev-{patient_id}-med-confirm"
    medication_adjustments = state.get("medication_adjustments", []) or []
    return {
        "pending_review": {
            "review_id": review_id,
            "type": "med_confirm",
            "payload": {
                "patient_id": patient_id,
                "medication_adjustments": medication_adjustments[-5:],
                "adjustment_count": len(medication_adjustments),
                "recent_alerts": (state.get("medication_alerts", []) or [])[-5:],
                "vital_trend": state.get("vital_signs", [])[-6:],
                "current_meds": medication_adjustments,
                "abnormal_labs": _get_abnormal_labs(state),
                "ai_remark": state.get("latest_round", {}).get("assessment", ""),
                "ddx_top": (state.get("ddx_list") or [])[:3],
            },
        },
        "med_confirm_status": "pending",
        "interrupt_pending": True,
    }


async def node_doctor_discharge_sign(state: dict) -> dict:
    """卡点③ 出院签字 — v1.3 §十一。

    幂等守卫：status in ("signed","rejected")。
    DOCTOR_AUTO_APPROVE=true 自动批准降级；
    否则挂起等待医生出院签字。
    """
    current_status = state.get("discharge_sign_status")
    if current_status in ("signed", "approved"):
        chain = state.get("document_chain", [])
        additions = [item for item in ("review_note", "discharge_signed") if item not in chain]
        if additions:
            return {"document_chain": chain + additions}
        return {}
    if current_status == "rejected":
        chain = state.get("document_chain", [])
        if "discharge_rejected" not in chain:
            return {"document_chain": chain + ["discharge_rejected"]}
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_doctor_discharge_sign: start, patient=%s", patient_id)

    if is_doctor_auto_approve():
        record("doctor_discharge_sign")
        return {
            "discharge_sign_status": "signed",
            "document_chain": state.get("document_chain", []) + ["review_note", "discharge_signed"],
        }

    review_id = f"rev-{patient_id}-discharge-sign"
    handoff_items = state.get("handoff_items", []) or []
    handoff_summary = [
        {"type": h.get("type", ""), "preview": (h.get("content", "") or "")[:80]}
        for h in handoff_items[:5]
    ]
    return {
        "pending_review": {
            "review_id": review_id,
            "type": "discharge_sign",
            "payload": {
                "patient_id": patient_id,
                "discharge_decision": state.get("discharge_decision"),
                "handoff_summary": handoff_summary,
                "handoff_count": len(handoff_items),
                "handoff_items": handoff_items,
                "template": (state.get("disease_template", {})
                             .get("name",
                                  state.get("disease_template", {})
                                  .get("disease_id", ""))),
                "discharge_criteria_check": state.get("discharge_criteria_check", {}),
                "vital_trend": state.get("vital_signs", [])[-6:],
                "complication_risks": state.get("clinical_alerts", []),
                "ddx_list": state.get("ddx_list", []),
                "medication_current": state.get("medication_adjustments", []),
                "latest_soap": state.get("latest_round", {}),
            },
        },
        "discharge_sign_status": "pending",
        "interrupt_pending": True,
    }
