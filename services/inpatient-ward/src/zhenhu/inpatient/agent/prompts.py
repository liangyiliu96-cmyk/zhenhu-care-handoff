"""Agent Prompt 模板 —— P1-1 集中管理所有 LLM prompt。

从 5 个节点文件中提取，按临床阶段分类：
- 入院期: HPI / ROS / PE / 出院标准评估
- 鉴别诊断: DDx 生成 / DDx 审核
- 监测期: 每日查房 / 调药建议 / 检验审阅
- 交接期: 出院交接 / 出院医嘱 / 交班摘要
- 评分: NEWS2 建议 / qSOFA 建议
- 用药: 药物相互作用 LLM 补充
"""

import json as _json


# ═══════════════════════════════════════════════════════════════
# 入院期 Prompts
# ═══════════════════════════════════════════════════════════════

def hpi_prompt(chief_complaint: str, hpi_focus: list, pmh_text: str) -> str:
    """现病史 (HPI) 叙事生成 — OLDCARTS 框架。"""
    focus_str = ", ".join(hpi_focus) if hpi_focus else "一般病史"
    return (
        f"根据以下入院信息生成中文现病史(HPI)叙事段落，遵循OLDCARTS框架"
        f"(起病/部位/持续时间/性质/加重与缓解因素/时效性/严重程度)：\n"
        f"主诉: {chief_complaint}\n"
        f"重点关注: {focus_str}\n"
        f"既往史: {pmh_text}\n"
        f'请生成约200字的中文叙事段落，仅返回JSON: {{"hpi_narrative": "..."}}'
    )


def ros_prompt(chief_complaint: str, ros_systems: list) -> str:
    """系统回顾 (ROS) 生成。"""
    return (
        f"根据患者主诉进行系统回顾(ROS)，对每个系统标注 (正常/无异常) 或具体异常发现：\n"
        f"主诉: {chief_complaint}\n"
        f"需审查系统: {', '.join(ros_systems) if ros_systems else '心血管/呼吸/消化/泌尿/神经/运动/皮肤'}\n"
        f"请返回JSON: {{\"ros\": {{ \"呼吸系统\": \"...\", ... }}}}，"
        f"每个系统用中文短语描述（5-15字），正常写\"无异常\"。"
    )


def pe_prompt(chief_complaint: str, hpi_narrative: str, vs_text: str,
              required_systems: list, focus_items: list) -> str:
    """体格检查 (PE) 叙事生成 — Bates 框架。"""
    sys_str = ", ".join(required_systems) if required_systems else "一般查体"
    items_str = ", ".join(focus_items) if focus_items else "常规查体"
    return (
        f"请根据以下信息生成中文体格检查(PE)叙事段落，遵循 Bates 体格检查指南：\n"
        f"主诉: {chief_complaint or '未提供'}\n"
        f"现病史: {hpi_narrative or '未提供'}\n"
        f"最新生命体征: {vs_text}\n"
        f"必查系统: {sys_str}\n"
        f"重点检查项: {items_str}\n"
        f"请生成约300字的中文查体叙事段落，格式按系统分类。"
        f"未指定系统应记为'未查'。"
        f'返回JSON: {{"pe_narrative": "..."}}'
    )


def discharge_criteria_prompt(cond_key: str, age: int, comorbidities: str,
                               recent_vs: str, template_name: str) -> str:
    """出院标准 LLM 语义评估。"""
    return (
        f"出院标准评估：'{cond_key}' 规则判定为不稳定。"
        f"请基于以下临床上下文判断患者是否实际已达到出院标准：\n"
        f"患者年龄: {age}\n"
        f"合并症: {comorbidities}\n"
        f"最近体征趋势: {recent_vs}\n"
        f"入院诊断: {template_name}\n"
        f"治疗经过: 已行相应治疗\n"
        f"回答仅 'stable' 或 'unstable'，不要解释。"
    )


def triage_prompt(risk_type: str, matched_factors: list, patient_data_str: str) -> str:
    """分诊风险评估 prompt（已内联，保留接口以备后用）。"""
    return (
        f"作为住院医师，基于以下临床数据评估患者风险等级（低/中/高）：\n"
        f"临床数据: {patient_data_str}\n"
        f"已匹配风险因子: {matched_factors}\n"
        f"返回JSON: {{\"risk_level\": \"low/medium/high\", \"recommendation\": \"...\"}}"
    )


# ═══════════════════════════════════════════════════════════════
# 鉴别诊断 Prompts
# ═══════════════════════════════════════════════════════════════

def ddx_prompt(cc: str, hpi: str, pe: str, allergies: str,
               labs: str, comorbidities: str, template_name: str) -> str:
    """鉴别诊断 (DDx) 生成。"""
    return (
        f"作为临床医生，基于以下信息生成鉴别诊断列表：\n"
        f"主诉: {cc}\n"
        f"现病史: {hpi[:400]}\n"
        f"体格检查: {pe[:400]}\n"
        f"过敏史: {allergies}\n"
        f"最近检验: {labs}\n"
        f"合并症: {comorbidities}\n"
        f"病种: {template_name}\n"
        f"请列出TOP 5鉴别诊断，每个含 diagnosis/icd10/likelihood(high|moderate|low)/key_findings/rationale。"
        f"仅返回JSON: {{\"ddx_list\": [...]}}"
    )


def ddx_reviewer_prompt(ddx_list: list) -> str:
    """DDx 审核完善 prompt。"""
    ddx_str = _json.dumps(ddx_list, ensure_ascii=False)[:500]
    return (
        f"作为上级医师，审核以下鉴别诊断列表的完整性和合理性。"
        f"当前DDx: {ddx_str}\n"
        f"请补充可能被遗漏的诊断（仅补充有临床依据的），返回JSON: {{\"additions\": [...]}}。"
        f"如无需补充，返回 {{\"additions\": []}}。"
    )


# ═══════════════════════════════════════════════════════════════
# 监测期 Prompts
# ═══════════════════════════════════════════════════════════════

def daily_round_prompt(template_name: str, risk: str, chief_complaint: str,
                       hpi: str, pe: str, ddx: list, latest_vs: dict,
                       vs_trend: str, labs_count: int, meds_count: int,
                       recent_labs_str: str, complication_monitoring: list) -> str:
    """每日查房 SOAP 笔记生成。"""
    return (
        f"作为住院医师，基于以下数据生成SOAP格式查房笔记（中文，专业临床语言）：\n"
        f"病种: {template_name}，风险等级: {risk}。\n"
        f"主诉: {chief_complaint}。\n"
        f"现病史: {hpi[:400]}。\n"
        f"查体关键发现: {pe[:400]}。\n"
        f"鉴别诊断: {_json.dumps([d.get('diagnosis', '') for d in ddx[:3]], ensure_ascii=False)}。\n"
        f"最新体征: {_json.dumps(latest_vs, ensure_ascii=False)}。\n"
        f"体征趋势: {vs_trend}。化验结果数: {labs_count}，用药调整数: {meds_count}。"
        f"{recent_labs_str}\n"
        f"需监测并发症: {_json.dumps(complication_monitoring, ensure_ascii=False)}\n"
        f"请返回JSON: {{\"chief_complaint\": \"患者主诉(1句)\", \"symptoms_since_last_round\": \"症状变化\", "
        f"\"response_to_treatment\": \"治疗反应评估\", \"next_labs\": \"下一步检查建议\"}}"
    )


def medication_adjust_prompt(template_name: str, alerts: list,
                              medication_protocol: dict, contraindications: list) -> str:
    """用药调整建议 prompt。"""
    return (
        f"基于以下体征异常生成用药调整建议（1-2句中文，含具体药物类别建议）："
        f"病种: {template_name}。"
        f"异常体征: {_json.dumps(alerts, ensure_ascii=False)}。"
        f"用药方案: {_json.dumps(medication_protocol, ensure_ascii=False)}\n"
        f"禁忌: {_json.dumps(contraindications, ensure_ascii=False)}\n"
        f'返回JSON: {{"suggestion": "...", "urgency": "routine/urgent/emergent"}}'
    )


def lab_review_prompt(template_name: str, new_labs: list) -> str:
    """检验审阅 prompt。"""
    labs_summary = [
        {"test": l.get("name", ""), "value": l.get("value", ""), "unit": l.get("unit", "")}
        for l in new_labs
    ]
    return (
        f"作为临床医生，审阅以下检验结果并给出专业判断。"
        f"患者病种: {template_name}。"
        f"检验结果: {_json.dumps(labs_summary, ensure_ascii=False)}。"
        f"请识别异常结果，给出1-2句综合解读和下一步建议（中文）。"
        f'返回JSON: {{"interpretation": "异常解读", '
        f'"abnormal_findings": [{{"test": "...", "finding": "...", "severity": "mild/moderate/severe"}}], '
        f'"recommendation": "建议"}}'
    )


# ═══════════════════════════════════════════════════════════════
# 交接期 Prompts
# ═══════════════════════════════════════════════════════════════

def handoff_prompt(template_name: str, risk: str, chief_complaint: str,
                   hpi: str, pe: str, ddx: list, instructions: list, vs: list) -> str:
    """出院交接个性化指导 prompt。"""
    return (
        f"为以下患者生成个性化出院指导补充（中文）：\n"
        f"病种: {template_name}，风险等级: {risk}。\n"
        f"主诉: {chief_complaint}。\n"
        f"现病史: {hpi[:200]}。\n"
        f"查体发现: {pe[:200]}。\n"
        f"鉴别诊断: {_json.dumps([d.get('diagnosis', '') for d in ddx[:3]], ensure_ascii=False)}。\n"
        f"模板基础指导: {_json.dumps([i.get('content', '')[:80] for i in instructions], ensure_ascii=False)}。\n"
        f"最新体征: {_json.dumps(vs[-2:] if vs else [], ensure_ascii=False)}。\n"
        f'请返回JSON: {{"personalized_notes": [{{"type": "medication/monitoring/followup", '
        f'"content": "具体个性化的指导内容(20-50字中文)"}}]}}，最多2条补充。'
    )


def discharge_orders_prompt(template_name: str, handoff_items: list,
                             patient_data: dict, hpi: str, pe: str, ddx: list) -> str:
    """出院医嘱生成 prompt。"""
    items_text = _json.dumps(
        [{"type": h.get("type", ""), "content": (h.get("content", "") or "")[:120]}
         for h in handoff_items[:5]],
        ensure_ascii=False
    )
    ddx_names = [d.get("diagnosis", "") for d in (ddx or [])[:3]]
    return (
        f"作为主任医师，为以下出院患者撰写正式出院医嘱（中文，结构化）：\n"
        f"病种: {template_name}\n"
        f"主诉: {patient_data.get('chief_complaint', '')}\n"
        f"现病史摘要: {hpi[:200]}\n"
        f"查体发现: {pe[:200]}\n"
        f"最终诊断: {', '.join(ddx_names) if ddx_names else '待补充'}\n"
        f"交接事项: {items_text}\n"
        f"请返回JSON with 出院带药(discharge_meds)、复查计划(followup_plan)、"
        f"健康宣教(patient_education)、注意事项(precautions) 各1-3条。"
    )


def nursing_prompt(latest_vs: dict, medications_administered: list,
                    inputs: list, outputs: list) -> str:
    """护理记录生成 prompt。"""
    return (
        f"作为责任护士，基于以下数据生成护理记录（中文，专业护理语言）：\n"
        f"生命体征: {_json.dumps(latest_vs, ensure_ascii=False) if latest_vs else '无'}\n"
        f"给药: {_json.dumps(medications_administered, ensure_ascii=False) if medications_administered else '无'}\n"
        f"入量: {_json.dumps(inputs, ensure_ascii=False) if inputs else '无'}\n"
        f"出量: {_json.dumps(outputs, ensure_ascii=False) if outputs else '无'}\n"
        f'返回JSON: {{"mar_summary": "...", "io_balance": "...", "nursing_interventions": [...], "alerts": [...]}}'
    )


def shift_summary_prompt(template_name: str, round_count: int, bp_now: str,
                          bp_before: str, spo2: str, hr: str,
                          news2: int | None, discharge: str,
                          alerts: list, hpi: str) -> str:
    """交班摘要 prompt。"""
    alerts_text = "; ".join(alerts[-3:]) if alerts else "无"
    return (
        f"生成一段约150字的中文交班要点，用于医生交接班。格式：简短自然语言段落。\n"
        f"患者: {template_name} | 查房轮次: 第{round_count}轮\n"
        f"当前体征: BP {bp_now} SpO2 {spo2}% HR {hr}\n"
        f"上次体征: BP {bp_before}\n"
        f"NEWS2评分: {news2} | 出院决定: {discharge or '未决定'}\n"
        f"临床告警: {alerts_text}\n"
        f"现病史: {hpi[:200]}\n"
        f"仅返回交班要点文本，不要前缀。"
    )


# ═══════════════════════════════════════════════════════════════
# 评分建议 Prompts
# ═══════════════════════════════════════════════════════════════

def news2_suggestion_prompt(total: int, risk: str, rr: str, spo2: str,
                              hr: str, sbp: str, temp: str) -> str:
    """NEWS2 临床行动建议。"""
    return (
        f"患者NEWS2评分={total}（{risk}风险），体征: RR={rr} SpO2={spo2} HR={hr} SBP={sbp} Temp={temp}\n"
        f"请用一句话（30字内）给出最优先的临床行动建议。不要解释。"
    )


def qsofa_suggestion_prompt(total: int, rr: str, sbp: str, gcs: str) -> str:
    """qSOFA 临床行动建议。"""
    return (
        f"患者qSOFA评分={total}（高风险），体征: RR={rr} SBP={sbp} GCS={gcs}\n"
        f"请用一句话（30字内）给出最优先的临床行动建议。不要解释。"
    )


# ═══════════════════════════════════════════════════════════════
# 用药 Prompts
# ═══════════════════════════════════════════════════════════════

def drug_interaction_prompt(all_med_names: list, pre_admission_meds: list,
                             allergies: list, medication_protocol: dict,
                             contraindications: list) -> str:
    """药物相互作用 LLM 补充检测。"""
    pre_names = [m.get("name", "") for m in pre_admission_meds]
    return (
        f"检查以下药物列表是否存在潜在的药物相互作用或禁忌。"
        f"出院药物: {_json.dumps(all_med_names, ensure_ascii=False)}。"
        f"院前用药: {_json.dumps(pre_names, ensure_ascii=False)}。"
        f"患者过敏史: {_json.dumps(allergies, ensure_ascii=False)}。"
        f"用药指南: {_json.dumps(medication_protocol, ensure_ascii=False)}\n"
        f"禁忌: {_json.dumps(contraindications, ensure_ascii=False)}\n"
        f'返回JSON: {{"additional_conflicts": [...], "warnings": [...]}}。'
        f"仅返回规则库可能遗漏的临床重要相互作用。"
    )
