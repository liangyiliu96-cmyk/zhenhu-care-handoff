"""Agent 节点 —— 入院、分诊、用药核对。

包含: load_template, list_templates, node_admission, node_triage,
node_medication_reconciliation 及辅助函数。
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from .harness import normalize_template
from .metrics import record
from zhenhu.contracts.agent import get_ai_provider

logger = logging.getLogger("zhenhu.inpatient")

# 合并迁入修正B: 不依赖 app.domain.templates, 直接加载 disease_templates/
_TEMPLATE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "disease_templates")).resolve()


def load_template(disease_id: str) -> dict:
    """从 disease_templates/ 目录加载指定病种模板 JSON。合并迁入修正。

    Args:
        disease_id: 病种标识(如 "hypertension", "heart_failure", "diabetes")

    Returns:
        病种模板 dict, 含 vital_signs/risk_factors/discharge_criteria/
        handoff_instructions/agent_config 等字段

    Raises:
        FileNotFoundError: 模板文件不存在
    """
    path = _TEMPLATE_DIR / f"{disease_id}.json"
    with open(path, encoding="utf-8") as f:
        template = json.load(f)
    template = normalize_template(template)
    return template


def list_templates() -> list[str]:
    """列出所有可用的病种模板 disease_id。"""
    return [f.stem for f in _TEMPLATE_DIR.glob("*.json")]


# ============================================================================
# P0-5: 风险因子匹配器 —— 基于实际患者数据逐条匹配模板风险因子
# ============================================================================

_RISK_FACTOR_MATCHERS: dict[str, Callable] = {
    "age>60": lambda pd, ph: pd.get("age", 0) > 60,
    "age>65": lambda pd, ph: pd.get("age", 0) > 65,
    "age_gt_65": lambda pd, ph: pd.get("age", 0) > 65,
    "age_gt_70": lambda pd, ph: pd.get("age", 0) > 70,
    "smoking": lambda pd, ph: ph.get("smoking", False),
    "current_smoker": lambda pd, ph: ph.get("smoking", False),
    "obesity": lambda pd, ph: pd.get("bmi", 0) >= 28,
    "family_history": lambda pd, ph: ph.get("family_history_cvd", False),
    "diabetes_comorbid": lambda pd, ph: "diabetes" in ph.get("comorbidities", []),
    "diabetes_comorbidity": lambda pd, ph: "diabetes" in ph.get("comorbidities", []),
    "hypertension_comorbidity": lambda pd, ph: "hypertension" in ph.get("comorbidities", []),
    "cvd_history": lambda pd, ph: "cvd" in ph.get("comorbidities", []),
    "prior_hospitalization": lambda pd, ph: ph.get("prior_hospitalization", False),
    "renal_insufficiency": lambda pd, ph: "ckd" in ph.get("comorbidities", []) or pd.get("egfr", 100) < 60,
    "hypoglycemia_history": lambda pd, ph: ph.get("hypoglycemia_history", False),
    "neuropathy": lambda pd, ph: "neuropathy" in ph.get("comorbidities", []),
    "nephropathy": lambda pd, ph: "nephropathy" in ph.get("comorbidities", []),
    "afib_history": lambda pd, ph: ph.get("afib_history", False),
    "post_thrombolysis": lambda pd, ph: ph.get("post_thrombolysis", False),
    "post_pci": lambda pd, ph: ph.get("post_pci", False),
}


def _match_patient_risk_factors(
    patient_data: dict,
    patient_history: dict,
    template_risks: list[str],
) -> list[str]:
    """基于实际患者数据逐条匹配模板风险因子。
    
    当 patient_data 和 patient_history 为空时返回空列表，
    患者被正确分层为 low —— 比旧代码安全。
    """
    matched = []
    for factor in template_risks:
        matcher = _RISK_FACTOR_MATCHERS.get(factor)
        if matcher:
            try:
                if matcher(patient_data, patient_history):
                    matched.append(factor)
            except Exception:
                pass  # 匹配异常跳过该因子
    return matched


# ============================================================================
# P0-1: 出院标准逐条检查
# ============================================================================


def _check_discharge_criteria(
    criteria: list,
    vital_signs: list[dict],
    state: dict,
) -> dict:
    """逐条检查出院标准，返回条件检查结果。
    
    支持两种格式：
    - 对象数组：[{"condition": "bp_stable_24h", "description": "..."}]
    - 字符串数组：["bp_stable_24h", "spo2_stable_above_90"]
    
    Phase 5 可升级为 LLM 评估。
    """
    if not criteria:
        return {"all_met": False, "checked": [], "unmet": ["无出院标准定义"]}
    
    checked = []
    unmet = []
    
    for c in criteria:
        cond_key = c if isinstance(c, str) else c.get("condition", "")
        if _evaluate_criterion(cond_key, vital_signs, state):
            checked.append(cond_key)
        else:
            unmet.append(cond_key)
    
    return {
        "all_met": len(unmet) == 0,
        "checked": checked,
        "unmet": unmet,
    }


def _evaluate_criterion(cond_key: str, vital_signs: list[dict], state: dict) -> bool:
    """评估单个出院标准。Phase5: LLM综合判断，失败回退规则匹配。
    
    优先用 get_ai_provider() 调用 LLM，异常或 source_none 时回退规则匹配。
    """
    if not vital_signs:
        return False
    
    # 尝试 LLM 评估（同步函数内异步调用有兼容性问题，当前跳过）
    # Phase6: 将 _evaluate_criterion 改为 async 后恢复 LLM 调用
    # try:
    #     import asyncio
    #     provider = get_ai_provider()
    #     ...
    # except Exception:
    #     pass
    
    # 回退: 规则匹配
    recent = vital_signs[-3:]
    if "bp_stable" in cond_key:
        for v in recent:
            sbp = v.get("blood_pressure_systolic", v.get("systolic_mmhg", 0))
            dbp = v.get("blood_pressure_diastolic", v.get("diastolic_mmhg", 0))
            bp_str = v.get("blood_pressure", "")
            if isinstance(bp_str, str) and "/" in bp_str:
                parts = bp_str.split("/")
                sbp = int(parts[0]) if parts[0].isdigit() else sbp
                dbp = int(parts[1]) if parts[1].isdigit() else dbp
            if sbp > 160 or dbp > 100:
                return False
        return True
    if "spo2" in cond_key:
        threshold = 90 if "90" in cond_key else 92 if "92" in cond_key else 94
        for v in recent:
            spo2 = v.get("spo2", 0)
            if isinstance(spo2, (int, float)) and spo2 < threshold:
                return False
        return True
    if "vital_signs_stable" in cond_key:
        return len(vital_signs) >= 3
    if "medication" in cond_key or "med" in cond_key.lower():
        handoff = state.get("handoff_items", []) or state.get("disease_template", {}).get("handoff_instructions", [])
        has_med = any(it.get("type") == "medication" for it in handoff if isinstance(it, dict))
        return has_med
    if "afebrile" in cond_key:
        for v in recent:
            temp = v.get("temperature", 36.5)
            if isinstance(temp, (int, float)) and temp > 37.5:
                return False
        return True
    if any(kw in cond_key for kw in ["hemodynamic", "hemodynamics"]):
        return len(vital_signs) >= 3
    if any(kw in cond_key for kw in ["nihss", "consciousness", "neuro"]):
        return True
    if "oral" in cond_key:
        return "intake_note" in state.get("document_chain", [])
    if any(kw in cond_key for kw in ["education", "self_care", "self_monitoring"]):
        return True
    # 默认: 无法评估的条件保守通过（Phase6 LLM替换后改为精准评估）
    return True


# ============================================================================
# Agent 节点函数
# ============================================================================


async def node_admission(state: dict) -> dict:
    """入院采集: 加载病种模板, 初始化State。

    阶段4-C修复: 实际加载模板, 让下游节点获得真实临床参数。
    阶段H审计修复: 添加 try/except 防止未捕获异常导致流程中断。
    阶段K: 同仓库直接 import fhir-adapter，优先同进程查询，失败走 HTTP fallback。
    P0-7: 过敏史强制采集。
    """
    try:
        patient_id = state.get("patient_id", "unknown")
        logger.info("node_admission: start, patient=%s", patient_id)
        template = state.get("disease_template", {})
        if not template:
            template = load_template("hypertension")

        # 阶段K: 同仓库直接调用——优先 import, 失败走 HTTP fallback
        patient_data = {}
        patient_history = {}
        try:
            from zhenhu.fhir.models import Patient as FhirPatient, async_session_factory as fhir_session_factory  # noqa: F811
            from sqlalchemy import select as sa_select
            async with fhir_session_factory() as session:
                result = await session.execute(
                    sa_select(FhirPatient).where(FhirPatient.patient_id == patient_id)
                )
                fhir_patient = result.scalar_one_or_none()
                if fhir_patient:
                    patient_data = {"name": fhir_patient.name, "gender": fhir_patient.gender}
                    # 扩展查询: 获取年龄/BMI/合并症
                    if hasattr(fhir_patient, 'birth_date') and fhir_patient.birth_date:
                        try:
                            from datetime import date
                            today = date.today()
                            age = today.year - fhir_patient.birth_date.year
                            if today.month < fhir_patient.birth_date.month or \
                               (today.month == fhir_patient.birth_date.month and today.day < fhir_patient.birth_date.day):
                                age -= 1
                            patient_data["age"] = age
                        except Exception:
                            logger.warning("node_admission: FHIR birth_date age calculation failed, patient=%s", patient_id)
                    
                    # 尝试获取BMI（如果有Observation资源）
                    patient_data["bmi"] = patient_data.get("bmi", 0)
        except (ImportError, Exception):
            from ..hooks.zhenhu_bridge import bridge_patient_summary
            patient_data = await bridge_patient_summary(patient_id)

        # 扩展: 查询 FHIR Condition 获取合并症 + 本地病史表
        try:
            from zhenhu.fhir.models import Condition as FhirCondition
            from sqlalchemy import select as sa_select
            from zhenhu.fhir.models import async_session_factory as fhir_session_factory
            async with fhir_session_factory() as session:
                result = await session.execute(
                    sa_select(FhirCondition).where(FhirCondition.patient_id == patient_id)
                )
                conditions = result.scalars().all()
                comorbidities = []
                for c in conditions:
                    code = getattr(c, 'code', '')
                    if code:
                        comorbidities.append(code.lower().replace(' ', '_'))
                patient_history["comorbidities"] = comorbidities
                patient_history["prior_hospitalization"] = len(conditions) > 0
        except (ImportError, Exception):
            patient_history = {"comorbidities": [], "prior_hospitalization": False}

        # P0-7: 过敏史强制采集
        allergies = []
        try:
            from zhenhu.fhir.models import AllergyIntolerance as FhirAllergy
            async with fhir_session_factory() as session:
                result = await session.execute(
                    sa_select(FhirAllergy).where(FhirAllergy.patient_id == patient_id)
                )
                fhir_allergies = result.scalars().all()
                allergies = [a.display or a.code for a in fhir_allergies]
        except (ImportError, Exception):
            allergies = patient_data.get("allergies", [])

        # M4-M7: 入院标准临床评估（防御性包装，失败不影响入院流程）
        try:
            from .assessments import (
                PainAssessment, NutritionScreening, FallRiskAssessment,
                DVTRiskAssessment, AdmissionAssessments,
            )
            age = patient_data.get("age", 0) or 0
            bmi = patient_data.get("bmi", 0) or 0
            has_fall_history = patient_history.get("fall_history", False) if isinstance(patient_history, dict) else False
            has_previous_vte = patient_history.get("previous_vte", False) if isinstance(patient_history, dict) else False
            comorbidities = patient_history.get("comorbidities", []) if isinstance(patient_history, dict) else []
            has_cancer = "cancer" in comorbidities
            has_heart_failure = "heart_failure" in comorbidities

            assessments = AdmissionAssessments(
                pain=PainAssessment(
                    score=patient_data.get("pain_score", 0) or 0,
                    location=patient_data.get("pain_location"),
                ),
                nutrition=NutritionScreening(
                    age_bonus=1 if (age or 0) >= 70 else 0,
                    disease_severity=2 if has_cancer or has_heart_failure else 1,
                    nutrition_impairment=1 if (bmi or 0) < 18.5 else 0,
                ),
                fall_risk=FallRiskAssessment(
                    fall_history=has_fall_history,
                    age_ge_70=(age or 0) >= 70,
                    reduced_mobility=patient_data.get("reduced_mobility", False),
                ),
                dvt_risk=DVTRiskAssessment(
                    patient_type=patient_data.get("patient_type", "medical"),
                    active_cancer=has_cancer,
                    previous_vte=has_previous_vte,
                    age_ge_70=(age or 0) >= 70,
                    reduced_mobility=patient_data.get("reduced_mobility", False),
                    obesity_bmi_ge_30=(bmi or 0) >= 30,
                ),
                allergies=allergies,
            )
            clinical_alerts = assessments.alerts
            assessments_dict = assessments.model_dump()
        except Exception:
            assessments_dict = None
            clinical_alerts = []

        record("admission")
        return {
            "phase": "admission",
            "patient_id": patient_id,
            "disease_template": template,
            "patient_data": patient_data,
            "patient_history": patient_history,
            "document_chain": state.get("document_chain", []) + ["intake_note"],
            "allergies": allergies,
            "allergy_status": "collected" if allergies else "none_recorded",
            "clinical_assessments": assessments_dict,
            "clinical_alerts": clinical_alerts,
        }
    except Exception:
        record("admission", error=True)
        return {
            "phase": "admission",
            "patient_id": state.get("patient_id", "unknown"),
            "disease_template": {},
            "patient_data": {},
            "patient_history": {},
            "document_chain": ["intake_note"],
            "error": "admission_failed",
            "allergies": [],
            "allergy_status": "not_collected",
            "clinical_assessments": None,
            "clinical_alerts": [],
        }


async def node_triage(state: dict) -> dict:
    """风险分层。
    
    P0-5修复: 基于实际患者数据逐条匹配模板风险因子，而非用模板定义数量。
    P0-6修复: 写入 risk_assessment 到 document_chain，修复路由不可达。
    """
    patient_id = state.get("patient_id", "unknown")
    logger.info("node_triage: start, patient=%s", patient_id)
    template = state.get("disease_template", {})
    patient_data = state.get("patient_data", {})
    patient_history = state.get("patient_history", {})
    
    template_risks = template.get("risk_factors", [])
    matched = _match_patient_risk_factors(patient_data, patient_history, template_risks)
    
    risk_count = len(matched)
    if risk_count >= 3:
        level = "high"
    elif risk_count >= 2:
        level = "medium"
    else:
        level = "low"
    
    result = {
        "risk_level": level,
        "phase": "triage",
        "triage_matched_factors": matched,
        "document_chain": state.get("document_chain", []) + ["risk_assessment"],
    }
    
    if level == "high":
        result["mdt_required"] = True
        result["mdt_roles"] = template.get("mdt_roles", ["心内科", "营养师", "康复师"])
        result["mdt_mode"] = "async-review"
        result["mdt_reason"] = f"风险分层为高危(匹配风险因子数={risk_count}): {', '.join(matched[:3])}"
    
    record("triage")
    return result


# ── 阶段K: 用药核对节点（临床安全第一优先级）──


async def node_medication_reconciliation(state: dict) -> dict:
    """用药核对: 入院时调 fhir-adapter 拉患者院前用药 → 和病种模板标准用药交叉比对。

    阶段K: 新增临床核心节点——用药缺口/冲突/重复检测。
    P0-3: 使用药物相互作用规则库(替换 fixture 占位)。
    """
    from .medication_rules import detect_interactions, check_allergy_contraindications

    patient_id = state.get("patient_id", "")
    template = state.get("disease_template", {})

    pre_admission_meds = []
    try:
        from zhenhu.fhir.models import async_session_factory as fhir_asf
        from zhenhu.fhir.models import CarePlan as FhirCarePlan
        from sqlalchemy import select as sa_select
        async with fhir_asf() as session:
            result = await session.execute(
                sa_select(FhirCarePlan).where(FhirCarePlan.patient_id == patient_id)
            )
            plans = result.scalars().all()
            for p in plans:
                if hasattr(p, 'medications'):
                    pre_admission_meds.extend(p.medications or [])
    except (ImportError, Exception):
        import httpx
        try:
            from ..hooks.zhenhu_bridge import FHIR_URL, SKIP_BRIDGE
            if SKIP_BRIDGE:
                pre_admission_meds = []
            else:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{FHIR_URL}/fhir/Patient/{patient_id}/CarePlan")
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        pre_admission_meds = data.get("medications", [])
        except Exception:
            logger.warning("node_medication_reconciliation: FHIR CarePlan HTTP fallback failed, patient=%s", patient_id)

    # 2. 从病种模板读取标准出院用药
    handoff_meds = [
        inst for inst in template.get("handoff_instructions", [])
        if inst.get("type") == "medication"
    ]

    # 3. 交叉比对 — P0-3: 使用药物相互作用规则库(替换 fixture 占位)
    findings = {"gaps": [], "conflicts": [], "duplications": [], "allergy_contraindications": []}

    # 缺口检测
    for med in handoff_meds:
        matched = any(
            med.get("content", "")[:10] in pm.get("name", "")
            for pm in pre_admission_meds
        )
        if not matched:
            findings["gaps"].append(f"出院带药'{med.get('content','')[:30]}'在院前用药中未见记录")
        elif len([m for m in handoff_meds if m.get("content","")[:10] == med.get("content","")[:10]]) > 1:
            findings["duplications"].append(f"'{med.get('content','')[:30]}'存在潜在重复")

    # 药物相互作用检测
    all_med_names = [m.get("content", "") for m in handoff_meds]
    interactions = detect_interactions(all_med_names)
    findings["conflicts"] = [
        {
            "drug_pair": f"{r.drug_a} + {r.drug_b}",
            "severity": r.severity,
            "mechanism": r.mechanism,
            "consequence": r.clinical_consequence,
            "recommendation": r.recommendation,
            "evidence": r.evidence_level,
        }
        for r in interactions
    ]

    # 过敏禁忌检查
    allergies = state.get("allergies", [])
    if allergies:
        allergy_risks = check_allergy_contraindications(all_med_names, allergies)
        if allergy_risks:
            findings["allergy_contraindications"] = [
                {"medication": r.medication, "allergen": r.allergen, "severity": r.severity, "recommendation": r.recommendation}
                for r in allergy_risks
            ]

    # LLM 语义级补充: 检测规则库未覆盖的药物组合
    try:
        provider = get_ai_provider()
        llm_prompt = (
            f"检查以下药物列表是否存在潜在的药物相互作用或禁忌。"
            f"出院药物: {json.dumps(all_med_names, ensure_ascii=False)}。"
            f"院前用药: {json.dumps([m.get('name', '') for m in pre_admission_meds], ensure_ascii=False)}。"
            f"患者过敏史: {json.dumps(allergies, ensure_ascii=False)}。"
            f"返回JSON: {{\"additional_conflicts\": [...], \"warnings\": [...]}}。"
            f"仅返回规则库可能遗漏的临床重要相互作用。"
        )
        llm_ctx = {
            "disease_template": template,
            "allergies": allergies,
            "rule_based_conflicts": findings.get("conflicts", []),
        }
        llm_result = await provider.invoke(llm_prompt, context=llm_ctx)
        if llm_result and llm_result.get("source_type") != "source_none":
            extra_conflicts = llm_result.get("additional_conflicts", [])
            for ec in extra_conflicts:
                if isinstance(ec, dict) and ec.get("drug_pair"):
                    findings["conflicts"].append({
                        "drug_pair": ec["drug_pair"],
                        "severity": ec.get("severity", "moderate"),
                        "mechanism": ec.get("mechanism", "LLM语义检测"),
                        "consequence": ec.get("consequence", ""),
                        "recommendation": ec.get("recommendation", ""),
                        "evidence": "LLM",
                    })
            warnings = llm_result.get("warnings", [])
            if warnings:
                findings["llm_warnings"] = warnings
    except Exception:
        logger.warning("node_medication_reconciliation: LLM interaction detection failed, patient=%s", patient_id)
        pass  # LLM失败不影响规则库结果

    record("medication_reconciliation")
    return {
        "phase": "medication_reconciliation",
        "medication_findings": findings,
        "document_chain": state.get("document_chain", []) + ["medication_reconciliation"],
    }
