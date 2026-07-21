"""Deterministic fictional patient pack used by the two-department demo."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEMO_PACK_VERSION = "2026-07-21.1"
DEMO_DEPARTMENTS = {"心内科": 10, "呼吸科": 10}
LEGACY_DEMO_PATIENT_IDS = frozenset({"demo-dashboard-care"})

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "disease_templates"


def _case(
    patient_id: str,
    department: str,
    template_id: str,
    name: str,
    age: int,
    gender: str,
    diagnosis: str,
    scenario: str,
    phase: str,
    risk_level: str,
    vitals: dict[str, Any],
    labs: list[dict[str, Any]],
    *,
    pending_review: str | None = None,
    alert: str | None = None,
    follow_up: bool = False,
    discharge_ready: bool = False,
    nursing_action: str = "复核生命体征、执行医嘱并完成床旁宣教。",
) -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "department": department,
        "template_id": template_id,
        "name": name,
        "age": age,
        "gender": gender,
        "diagnosis": diagnosis,
        "scenario": scenario,
        "phase": phase,
        "risk_level": risk_level,
        "vitals": vitals,
        "labs": labs,
        "pending_review": pending_review,
        "alert": alert,
        "follow_up": follow_up,
        "discharge_ready": discharge_ready,
        "nursing_action": nursing_action,
    }


CARDIOLOGY_PATIENTS = (
    _case("demo-card-hf-acute", "心内科", "heart_failure", "李静安", 72, "female", "急性失代偿性心力衰竭", "容量负荷增加，利尿治疗期间需要复核肾功能和血钾。", "monitoring", "high", {"systolic_mmhg": 98, "diastolic_mmhg": 62, "heart_rate": 102, "spo2": 91, "temperature": 36.8, "weight": 73.2}, [{"name": "NT-proBNP", "value": 4260, "unit": "pg/mL"}, {"name": "肌酐", "value": 158, "unit": "umol/L"}, {"name": "血钾", "value": 3.2, "unit": "mmol/L"}], pending_review="med_confirm", alert="低氧与低钾风险，需复核利尿剂及补钾方案。", nursing_action="记录出入量、每日体重和氧疗反应，复核补钾医嘱。"),
    _case("demo-card-post-pci", "心内科", "cad", "周铭远", 61, "male", "冠心病 PCI 术后恢复期", "术后第 2 天，双联抗血小板治疗和穿刺点观察。", "monitoring", "medium", {"systolic_mmhg": 124, "diastolic_mmhg": 76, "heart_rate": 72, "spo2": 98, "temperature": 36.6}, [{"name": "肌钙蛋白I", "value": 0.08, "unit": "ng/mL"}, {"name": "血红蛋白", "value": 132, "unit": "g/L"}], nursing_action="评估桡动脉穿刺点、执行双抗宣教并记录出血征象。"),
    _case("demo-card-af-anticoag", "心内科", "atrial_fibrillation", "孙晓蓉", 77, "female", "心房颤动伴抗凝治疗", "肾功能波动，口服抗凝药剂量需由医生审核。", "review", "medium", {"systolic_mmhg": 118, "diastolic_mmhg": 70, "heart_rate": 108, "spo2": 97, "temperature": 36.5}, [{"name": "肌酐", "value": 142, "unit": "umol/L"}, {"name": "eGFR", "value": 34, "unit": "mL/min/1.73m2"}], pending_review="med_confirm", nursing_action="观察皮肤黏膜出血、核对抗凝药与肾功能复查时间。"),
    _case("demo-card-htn-crisis", "心内科", "hypertension", "赵文博", 56, "male", "高血压急症恢复期", "降压后仍有波动，出院条件尚未满足。", "discharge", "medium", {"systolic_mmhg": 168, "diastolic_mmhg": 98, "heart_rate": 80, "spo2": 98, "temperature": 36.5}, [{"name": "肌酐", "value": 96, "unit": "umol/L"}], alert="收缩压仍高于出院目标，暂不建议出院。", nursing_action="复测双侧血压，评估头痛和视物模糊症状。"),
    _case("demo-card-hf-handoff", "心内科", "heart_failure", "陈慧兰", 69, "female", "慢性心衰稳定期", "容量状态已改善，等待医生签字和出院交接。", "handoff", "low", {"systolic_mmhg": 116, "diastolic_mmhg": 72, "heart_rate": 74, "spo2": 97, "temperature": 36.4, "weight": 64.1}, [{"name": "NT-proBNP", "value": 810, "unit": "pg/mL"}, {"name": "血钾", "value": 4.2, "unit": "mmol/L"}], pending_review="discharge_sign", follow_up=True, discharge_ready=True, nursing_action="完成每日体重、限盐限水和恶化症状识别的教回示。"),
    _case("demo-card-chest-pain", "心内科", "cad", "吴昊然", 48, "male", "胸痛待鉴别诊断", "胸痛复发，AI 查房摘要建议复核急性冠脉综合征与主动脉夹层风险。", "review", "high", {"systolic_mmhg": 146, "diastolic_mmhg": 88, "heart_rate": 96, "spo2": 96, "temperature": 36.7}, [{"name": "肌钙蛋白I", "value": 0.19, "unit": "ng/mL"}, {"name": "D-二聚体", "value": 1.3, "unit": "mg/L"}], pending_review="doctor_confirm", alert="胸痛伴肌钙蛋白升高，需医生及时完成鉴别诊断。", nursing_action="持续心电监护，记录胸痛评分和放射痛变化。"),
    _case("demo-card-acs-monitor", "心内科", "cad", "何国强", 64, "male", "急性冠脉综合征", "抗缺血治疗期间监测胸痛、心电与肌钙蛋白趋势。", "monitoring", "high", {"systolic_mmhg": 106, "diastolic_mmhg": 68, "heart_rate": 90, "spo2": 95, "temperature": 36.7}, [{"name": "肌钙蛋白I", "value": 1.82, "unit": "ng/mL"}, {"name": "LDL-C", "value": 3.1, "unit": "mmol/L"}], alert="肌钙蛋白升高，需持续胸痛与心律失常监测。", nursing_action="每班评估胸痛，核对抗栓治疗和出血风险。"),
    _case("demo-card-cardiorenal", "心内科", "heart_failure", "马春梅", 74, "female", "心肾综合征", "利尿反应有限，已发起心内科与肾内科 MDT。", "monitoring", "high", {"systolic_mmhg": 104, "diastolic_mmhg": 66, "heart_rate": 88, "spo2": 93, "temperature": 36.6, "weight": 70.8}, [{"name": "肌酐", "value": 204, "unit": "umol/L"}, {"name": "尿素氮", "value": 14.8, "unit": "mmol/L"}], alert="肾功能恶化且氧饱和度偏低，等待 MDT 建议。", nursing_action="严格记录出入量，观察水肿与尿量变化。"),
    _case("demo-card-pacemaker", "心内科", "cad", "唐海波", 66, "male", "永久起搏器植入术后", "术后第 1 天，伤口、制动与起搏参数观察。", "monitoring", "medium", {"systolic_mmhg": 122, "diastolic_mmhg": 74, "heart_rate": 62, "spo2": 98, "temperature": 36.5}, [{"name": "血红蛋白", "value": 128, "unit": "g/L"}], nursing_action="观察切口渗血、保持患侧上肢制动并进行起搏器注意事项宣教。"),
    _case("demo-card-hf-followup", "心内科", "heart_failure", "方玉琴", 70, "female", "心衰出院后随访", "出院第 7 天反馈体重上升和夜间气促，需要升级处置。", "follow_up", "high", {"systolic_mmhg": 128, "diastolic_mmhg": 78, "heart_rate": 86, "spo2": 94, "temperature": 36.5, "weight": 68.9}, [{"name": "血钾", "value": 4.1, "unit": "mmol/L"}], follow_up=True, discharge_ready=True, alert="随访反馈体重 3 天增加 2.2 kg 并出现夜间气促。", nursing_action="电话确认呼吸困难程度、用药依从性并协助加急复诊。"),
)

RESPIRATORY_PATIENTS = (
    _case("demo-resp-copd-ae", "呼吸科", "copd", "刘德昌", 68, "male", "慢阻肺急性加重", "氧疗与雾化治疗期间，需复核血气及吸入装置使用。", "monitoring", "high", {"systolic_mmhg": 132, "diastolic_mmhg": 80, "heart_rate": 104, "spo2": 87, "temperature": 37.4, "respiratory_rate": 29}, [{"name": "PaCO2", "value": 56, "unit": "mmHg"}, {"name": "CRP", "value": 38, "unit": "mg/L"}], alert="低氧和二氧化碳潴留风险，需评估氧疗目标。", nursing_action="记录氧疗流量、呼吸功和雾化吸入技术。"),
    _case("demo-resp-cap", "呼吸科", "pneumonia", "林雪晴", 54, "female", "社区获得性肺炎", "发热与炎症指标仍高，抗菌药治疗效果待评估。", "monitoring", "high", {"systolic_mmhg": 112, "diastolic_mmhg": 70, "heart_rate": 102, "spo2": 93, "temperature": 38.7, "respiratory_rate": 24}, [{"name": "白细胞", "value": 15.4, "unit": "10^9/L"}, {"name": "CRP", "value": 126, "unit": "mg/L"}], alert="持续高热伴炎症指标升高，需复核感染控制情况。", nursing_action="监测体温曲线、痰液性状并完成抗菌药不良反应观察。"),
    _case("demo-resp-asthma", "呼吸科", "asthma", "许雨桐", 32, "female", "支气管哮喘急性发作恢复期", "症状已改善，等待吸入技术和行动计划教回示后出院。", "discharge", "low", {"systolic_mmhg": 110, "diastolic_mmhg": 68, "heart_rate": 76, "spo2": 98, "temperature": 36.5, "respiratory_rate": 18}, [{"name": "PEF", "value": 410, "unit": "L/min"}], follow_up=True, discharge_ready=True, nursing_action="核对吸入器操作，完成哮喘行动计划和急性发作警示教育。"),
    _case("demo-resp-pe", "呼吸科", "pe", "郭志明", 59, "male", "肺栓塞抗凝治疗", "低分子肝素向口服抗凝转换，需审核剂量与出血风险。", "review", "medium", {"systolic_mmhg": 118, "diastolic_mmhg": 72, "heart_rate": 92, "spo2": 95, "temperature": 36.6, "respiratory_rate": 20}, [{"name": "D-二聚体", "value": 2.8, "unit": "mg/L"}, {"name": "血小板", "value": 142, "unit": "10^9/L"}], pending_review="med_confirm", nursing_action="观察皮肤黏膜出血、呼吸困难变化并核对抗凝交接。"),
    _case("demo-resp-sepsis-recovery", "呼吸科", "sepsis", "陆芳华", 63, "female", "脓毒症后呼吸衰竭恢复期", "从 ICU 转入病房，进行氧疗递减、营养风险和康复评估。", "monitoring", "high", {"systolic_mmhg": 108, "diastolic_mmhg": 66, "heart_rate": 96, "spo2": 92, "temperature": 37.3, "respiratory_rate": 23}, [{"name": "乳酸", "value": 2.1, "unit": "mmol/L"}, {"name": "白细胞", "value": 12.7, "unit": "10^9/L"}], alert="转出 ICU 后氧合仍不稳定，需要多学科协同。", nursing_action="评估意识、氧疗耐受、吞咽及营养风险。"),
    _case("demo-resp-ild-oxygen", "呼吸科", "copd", "沈建民", 71, "male", "间质性肺病伴活动性低氧", "静息尚可，活动后氧饱和度下降，准备居家氧疗交接。", "handoff", "medium", {"systolic_mmhg": 126, "diastolic_mmhg": 74, "heart_rate": 84, "spo2": 94, "temperature": 36.5, "respiratory_rate": 22}, [{"name": "DLCO", "value": 42, "unit": "%pred"}], follow_up=True, discharge_ready=True, nursing_action="指导活动氧疗、氧气设备安全和呼吸康复训练。"),
    _case("demo-resp-bronchiectasis", "呼吸科", "pneumonia", "彭晓云", 58, "female", "支气管扩张伴咯血", "少量咯血仍反复，需监测出血量与体位管理。", "monitoring", "high", {"systolic_mmhg": 124, "diastolic_mmhg": 76, "heart_rate": 98, "spo2": 95, "temperature": 37.1, "respiratory_rate": 22}, [{"name": "血红蛋白", "value": 104, "unit": "g/L"}, {"name": "CRP", "value": 46, "unit": "mg/L"}], alert="存在活动性咯血风险，需记录咯血量并及时升级。", nursing_action="记录咯血颜色和体积，执行患侧卧位及气道清理。"),
    _case("demo-resp-chemo-infection", "呼吸科", "sepsis", "罗子昂", 46, "male", "化疗后感染评估", "中性粒细胞减少伴发热，等待医生确认抗菌药和隔离方案。", "review", "high", {"systolic_mmhg": 102, "diastolic_mmhg": 64, "heart_rate": 108, "spo2": 94, "temperature": 38.5, "respiratory_rate": 24}, [{"name": "中性粒细胞", "value": 0.4, "unit": "10^9/L"}, {"name": "PCT", "value": 1.8, "unit": "ng/mL"}], pending_review="doctor_confirm", alert="发热性中性粒细胞减少，需要优先完成抗感染处置。", nursing_action="执行保护性隔离，监测寒战和感染灶症状。"),
    _case("demo-resp-osa-copd", "呼吸科", "copd", "姚淑琴", 65, "female", "睡眠呼吸暂停合并慢阻肺", "夜间无创通气依从性评估，日间症状稳定。", "monitoring", "medium", {"systolic_mmhg": 130, "diastolic_mmhg": 78, "heart_rate": 74, "spo2": 96, "temperature": 36.4, "respiratory_rate": 18}, [{"name": "PaCO2", "value": 46, "unit": "mmHg"}], nursing_action="核对无创通气面罩密闭性、夜间使用时长和皮肤受压情况。"),
    _case("demo-resp-copd-followup", "呼吸科", "copd", "丁志刚", 73, "male", "慢阻肺出院后随访", "出院第 5 天反馈气促加重、痰量增加，需要电话评估与升级。", "follow_up", "high", {"systolic_mmhg": 136, "diastolic_mmhg": 82, "heart_rate": 92, "spo2": 90, "temperature": 37.2, "respiratory_rate": 24}, [{"name": "CRP", "value": 22, "unit": "mg/L"}], follow_up=True, discharge_ready=True, alert="随访反馈气促加重及痰量增加，提示再急性加重风险。", nursing_action="电话核实吸入药依从性、氧饱和度和急诊就医指征。"),
)

DEMO_PATIENT_IDS = tuple(item["patient_id"] for item in CARDIOLOGY_PATIENTS + RESPIRATORY_PATIENTS)


def _load_template(template_id: str, department: str) -> dict[str, Any]:
    path = _TEMPLATE_DIR / f"{template_id}.json"
    try:
        template = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        template = {"disease_id": template_id, "name": template_id}
    template["department"] = department
    return template



def _template_citations(template: dict[str, Any], *, retrieved_at: str) -> list[dict[str, Any]]:
    """Expose source-controlled template provenance for a fictional case."""
    disease_id = str(template.get("disease_id") or "unknown")
    name = str(template.get("name") or disease_id)
    monitoring = str(template.get("monitoring_interval_hours") or "按病情动态评估")
    criteria = [
        str(item.get("description") or item.get("condition") or "").strip()
        for item in template.get("discharge_criteria") or []
        if isinstance(item, dict)
    ]
    excerpt = f"监测频率：{monitoring} 小时。出院条件：{'；'.join(item for item in criteria if item) or '以病种模板与医生评估为准。'}"
    return [{
        "citation_id": f"demo-template:{disease_id}",
        "knowledge_layer": "L3",
        "source": "disease_template",
        "title": f"{name}病种模板",
        "topic": name,
        "version": DEMO_PACK_VERSION,
        "excerpt": excerpt[:300],
        "retrieved_at": retrieved_at,
        "provenance": "demo_template",
    }]


def _demo_discharge_criteria(item: dict[str, Any]) -> dict[str, Any]:
    """Provide an explainable, deterministic pre-check for each demo patient."""
    discharge_ready = bool(item["discharge_ready"])
    phase = str(item["phase"])
    details = [
        {
            "key": "vital_signs_stable",
            "label": "生命体征保持稳定",
            "met": discharge_ready,
            "category": "monitoring",
            "action": "补充最新体征并重新评估",
        },
        {
            "key": "medication_titrated",
            "label": "用药方案已确认并达到出院要求",
            "met": discharge_ready or phase == "discharge",
            "category": "orders",
            "action": "完成用药方案确认或相关医嘱审核",
        },
        {
            "key": "self_care_education_done",
            "label": "完成患者自我管理教育",
            "met": discharge_ready or phase == "discharge",
            "category": "discharge",
            "action": "完成出院宣教、随访或交接准备",
        },
        {
            "key": "clinical_euvolemia_24h",
            "label": "临床状况稳定并满足观察要求",
            "met": discharge_ready,
            "category": "monitoring",
            "action": "完成连续观察并由医生复核本次查房结果",
        },
    ]
    unmet = [detail["key"] for detail in details if not detail["met"]]
    return {
        "all_met": not unmet,
        "checked": [detail["key"] for detail in details if detail["met"]],
        "unmet": unmet,
        "met_count": len(details) - len(unmet),
        "total_count": len(details),
        "details": details,
    }


def _demo_clinical_scores(state: dict[str, Any], *, calculated_at: str) -> dict[str, Any]:
    """Project deterministic scoring evidence for fictional demo cases only.

    The normal Agent nodes remain the source of truth in production.  Demo
    fixtures use the same pure scoring helpers, without running Agent or LLM
    nodes while reseeding the local presentation data.
    """
    from ..agent.nodes_scoring import _calc_padua, _load_thresholds, _score_range, _score_range_rev

    latest = (state.get("vital_signs") or [{}])[-1]
    template = state.get("disease_template") or {}
    thresholds = _load_thresholds()

    respiratory_rate = float(latest["respiratory_rate"])
    spo2 = float(latest["spo2"])
    temperature = float(latest["temperature"])
    systolic = float(latest.get("systolic_mmhg") or latest["systolic"])
    heart_rate = float(latest["heart_rate"])
    gcs = float(latest["gcs"])

    rr_points = _score_range(respiratory_rate, thresholds["news2_rr"])
    is_copd = template.get("disease_id") == "copd" or "COPD" in str(template.get("name") or "")
    spo2_points = _score_range_rev(
        spo2,
        thresholds["news2_spo2_scale2"] if is_copd else thresholds["news2_spo2_scale1"],
    ) if is_copd else _score_range(spo2, thresholds["news2_spo2_scale1"])
    temperature_points = _score_range(temperature, thresholds["news2_temp"])
    systolic_points = _score_range_rev(systolic, thresholds["news2_sbp"])
    heart_rate_points = _score_range(heart_rate, thresholds["news2_hr"])
    consciousness_points = 3 if gcs < 15 else 0
    news2_score = sum((rr_points, spo2_points, temperature_points, systolic_points, heart_rate_points, consciousness_points))
    news2_risk = "high" if news2_score >= 7 else "medium" if news2_score >= 5 else "low"

    qsofa_basis = [
        ("呼吸频率", respiratory_rate, respiratory_rate >= 22),
        ("收缩压", systolic, systolic <= 100),
        ("GCS", gcs, gcs < 15),
    ]
    qsofa_score = sum(1 for _, _, positive in qsofa_basis if positive)
    padua_score, padua_factors = _calc_padua(state)

    return {
        "news2_score": news2_score,
        "news2_risk": news2_risk,
        "qsofa_score": qsofa_score,
        "qsofa_risk": "high" if qsofa_score >= 2 else "low",
        "padua_score": padua_score,
        "padua_risk": "high" if padua_score >= 4 else "low",
        "clinical_score_details": {
            "source": "demo_deterministic_projection",
            "calculated_at": calculated_at,
            "news2": {
                "status": "available",
                "basis": [
                    f"呼吸频率 {respiratory_rate:g} 次/分：{rr_points} 分",
                    f"血氧饱和度 {spo2:g}%：{spo2_points} 分（{'COPD量表2' if is_copd else '量表1'}）",
                    f"体温 {temperature:g}°C：{temperature_points} 分",
                    f"收缩压 {systolic:g} mmHg：{systolic_points} 分",
                    f"心率 {heart_rate:g} 次/分：{heart_rate_points} 分",
                    f"GCS {gcs:g}：{consciousness_points} 分",
                ],
            },
            "qsofa": {
                "status": "available",
                "basis": [
                    f"{label} {value:g}{' 次/分' if label == '呼吸频率' else ' mmHg' if label == '收缩压' else ''}：{'满足1分' if positive else '不满足，0分'}"
                    for label, value, positive in qsofa_basis
                ],
            },
            "padua": {
                "status": "available",
                "basis": padua_factors or ["未发现 Padua 规则触发因素"],
            },
        },
    }


def _demo_scoring_chain(item: dict[str, Any]) -> list[str]:
    chain = ["intake_note", "history_note", "pe_note", "daily_round_note", "nursing_note", "padua_scored", "vte_check"]
    if item["template_id"] != "stroke":
        chain.append("stroke_at_not_applicable")
    if item["patient_id"] in {"demo-card-cardiorenal", "demo-resp-sepsis-recovery"}:
        chain.append("mdt_triggered")
    return chain


def _demo_post_discharge_handoff(item: dict[str, Any]) -> dict[str, Any]:
    """Seed an actionable, not-yet-completed handoff for follow-up demos."""
    if not item["follow_up"]:
        return {}
    return {
        "bridge_result": {
            "status": "ok",
            "case_id": f"demo-handoff-{item['patient_id']}",
            "state": "created",
        },
        "handoff_acknowledged": False,
        "patient_confirmation_status": "pending",
        "patient_confirmation_requirements": ["handoff_acknowledgement", "teach_back"],
        "patient_confirmation_evidence": [],
    }


def build_demo_patient_states(now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Build the complete, fictional clinical states without invoking the Agent."""
    current = now or datetime.now(timezone.utc)
    observed_at = (current - timedelta(hours=1)).isoformat()
    follow_up_due = (current - timedelta(days=1)).isoformat()
    states: dict[str, dict[str, Any]] = {}

    for item in CARDIOLOGY_PATIENTS + RESPIRATORY_PATIENTS:
        template = _load_template(item["template_id"], item["department"])
        citations = _template_citations(template, retrieved_at=current.isoformat())
        latest_vitals = {"timestamp": observed_at, **deepcopy(item["vitals"])}
        latest_vitals.setdefault("respiratory_rate", 16)
        latest_vitals.setdefault("gcs", 15)
        pending_review = (
            {"type": item["pending_review"], "status": "pending", "requested_by": "演示病例"}
            if item["pending_review"]
            else None
        )
        follow_up_tasks = []
        if item["follow_up"]:
            follow_up_tasks.append({
                "id": f"{item['patient_id']}-follow-up-1",
                "title": "出院后症状与用药随访",
                "due_at": follow_up_due,
                "assignee": f"{item['department']}随访护士",
                "status": "pending",
                "note": "演示病例：请联系患者完成结构化随访。",
                "abnormal_feedback": item["risk_level"] == "high",
                "feedback_level": "abnormal" if item["risk_level"] == "high" else "normal",
            })
        state = {
            "patient_id": item["patient_id"],
            "department": item["department"],
            "demo_seed": True,
            "demo_pack_version": DEMO_PACK_VERSION,
            "demo_department": item["department"],
            "phase": item["phase"],
            "current_step": item["phase"],
            "risk_level": item["risk_level"],
            "patient_access": {"department": item["department"]},
            "patient_data": {
                "name": item["name"],
                "age": item["age"],
                "gender": item["gender"],
                "admission_number": f"ZH-{item['patient_id'].upper()[-8:]}",
                "mobile_phone": f"1550000{len(states) + 1000:04d}",
                "emergency_contact": "演示联系人",
                "is_demo_patient": True,
            },
            "patient_history": {
                "comorbidities": [item["diagnosis"]],
                "medications": ["演示医嘱，详见用药管理"],
                "prior_hospitalization": item["risk_level"] != "low",
            },
            "history_data": {"chief_complaint": item["scenario"], "hpi_narrative": item["scenario"]},
            "pe_data": {"pe_narrative": "生命体征与专科查体见本次查房摘要。"},
            "allergies": ["无已知药物过敏"],
            "disease_template": template,
            "vital_signs": [latest_vitals],
            "lab_results": deepcopy(item["labs"]),
            "clinical_alerts": [item["alert"]] if item["alert"] else [],
            "pending_review": pending_review,
            "medication_orders": [{
                "id": f"{item['patient_id']}-order-1",
                "medication": "演示治疗医嘱",
                "dose": "按方案执行",
                "frequency": "每日一次",
                "route": "口服",
                "status": "active",
            }],
            "nursing_records": [{
                "timestamp": observed_at,
                "source": "agent",
                "round_number": 1,
                "nursing_actions": item["nursing_action"],
                "alerts": [item["alert"]] if item["alert"] else [],
            }],
            "latest_round": {
                "round_number": 1,
                "subjective": item["scenario"],
                "objective": "已汇总体征、检验与用药信息。",
                "assessment": item["diagnosis"],
                "plan": "医生核对 AI 查房摘要后执行下一步临床处置。",
                "generation_source": "demo_seed",
                "review_status": "requires_clinician_review",
                "source_nodes": ["vital_signs", "lab_results", "daily_round_agent"],
                "citations": deepcopy(citations),
            },
            "round_history": [],
            "round_count": 1,
            "ddx_list": [{"diagnosis": item["diagnosis"], "likelihood": "high"}],
            "discharge_criteria_check": _demo_discharge_criteria(item),
            "discharge_decision": "approved" if item["discharge_ready"] else "pending",
            "discharge_sign_status": "signed" if item["follow_up"] else "",
            "follow_up_contact_registered": item["follow_up"],
            "handoff_items": ([{"type": "follow_up", "content": "已建立出院后随访任务。"}] if item["follow_up"] else []),
            "follow_up_tasks": follow_up_tasks,
            "document_chain": _demo_scoring_chain(item) + (["handoff_note", "discharge_bridge"] if item["follow_up"] else []),
            "stroke_antithrombotic_status": "not_applicable" if item["template_id"] != "stroke" else "pending",
            "clinical_evidence": citations,
            "last_updated": current.isoformat(),
        }
        state.update(_demo_post_discharge_handoff(item))
        state.update(_demo_clinical_scores(state, calculated_at=current.isoformat()))
        states[item["patient_id"]] = state
    return states
