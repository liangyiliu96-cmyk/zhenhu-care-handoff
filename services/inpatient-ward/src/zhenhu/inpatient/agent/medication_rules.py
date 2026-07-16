"""药物相互作用规则库。P0-3: 替换 node_medication_reconciliation 的 fixture 占位。

≥30对核心药物配对，覆盖心内/内分泌/呼吸/消化/神经/肿瘤常用药物组合。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================================
# 规则模型
# ============================================================================


class DrugInteractionRule(BaseModel):
    """药物相互作用规则。"""
    drug_a: str = Field(..., description="药物A通用名")
    drug_b: str = Field(..., description="药物B通用名")
    severity: Literal["contraindicated", "major", "moderate", "minor"] = Field(
        ..., description="严重程度"
    )
    mechanism: str = Field(..., description="相互作用机制")
    clinical_consequence: str = Field(..., description="临床后果")
    recommendation: str = Field(..., description="处理建议")
    evidence_level: str = Field(..., description="证据等级 A/B/C")
    source: str = Field(..., description="来源指南")


class AllergyContraindication(BaseModel):
    """过敏禁忌匹配结果。"""
    medication: str
    allergen: str
    severity: str
    recommendation: str


# ============================================================================
# 规则库 (≥30对)
# ============================================================================


MEDICATION_INTERACTION_RULES: list[DrugInteractionRule] = [
    # ── 抗凝 + NSAID ──
    DrugInteractionRule(
        drug_a="华法林", drug_b="布洛芬", severity="contraindicated",
        mechanism="NSAID抑制血小板+损伤胃黏膜+置换华法林蛋白结合",
        clinical_consequence="严重消化道出血风险，INR升高",
        recommendation="避免联用。必须联用时选择对INR影响小的NSAID(如塞来昔布)，并加用PPI。",
        evidence_level="A", source="ACCP抗栓指南(第10版)",
    ),
    DrugInteractionRule(
        drug_a="华法林", drug_b="双氯芬酸", severity="major",
        mechanism="NSAID抑制血小板+胃黏膜损伤+蛋白结合置换",
        clinical_consequence="消化道出血风险显著增加",
        recommendation="避免联用或严密监测INR+加用PPI",
        evidence_level="A", source="ACCP抗栓指南(第10版)",
    ),
    DrugInteractionRule(
        drug_a="阿司匹林", drug_b="布洛芬", severity="major",
        mechanism="布洛芬竞争性抑制阿司匹林对COX-1的不可逆乙酰化",
        clinical_consequence="阿司匹林抗血小板作用减弱",
        recommendation="布洛芬应在阿司匹林服用至少2h后使用，或换用对乙酰氨基酚",
        evidence_level="B", source="FDA药物安全通讯",
    ),
    DrugInteractionRule(
        drug_a="氯吡格雷", drug_b="布洛芬", severity="major",
        mechanism="双重抗血小板+NSAID增加消化道出血",
        clinical_consequence="严重消化道出血风险",
        recommendation="必须联用时加用PPI",
        evidence_level="B", source="ESC NSTE-ACS指南2015",
    ),
    
    # ── ACEi/ARB + 保钾 ──
    DrugInteractionRule(
        drug_a="培哚普利", drug_b="螺内酯", severity="major",
        mechanism="ACEi减少醛固酮 → 减少钾排泄 + 螺内酯为醛固酮拮抗剂",
        clinical_consequence="致命性高钾血症(>6.0mmol/L)",
        recommendation="严密监测血钾(每周)，螺内酯≤25mg/d，血钾>5.0停用",
        evidence_level="A", source="ESC心衰指南2021",
    ),
    DrugInteractionRule(
        drug_a="缬沙坦", drug_b="螺内酯", severity="major",
        mechanism="ARB+醛固酮拮抗剂双重保钾",
        clinical_consequence="高钾血症风险",
        recommendation="监测血钾，螺内酯限25mg/d",
        evidence_level="A", source="ESC心衰指南2021",
    ),
    DrugInteractionRule(
        drug_a="卡托普利", drug_b="氨苯蝶啶", severity="contraindicated",
        mechanism="ACEi+保钾利尿剂双重保钾",
        clinical_consequence="致命性高钾血症",
        recommendation="禁止联用",
        evidence_level="A", source="中国高血压防治指南2018",
    ),
    
    # ── β-blocker + CCB ──
    DrugInteractionRule(
        drug_a="美托洛尔", drug_b="维拉帕米", severity="contraindicated",
        mechanism="双重负性肌力+负性传导+负性频率",
        clinical_consequence="严重心动过缓、房室传导阻滞、心衰恶化、心脏停搏",
        recommendation="禁止联用。如必须联用，使用二氢吡啶类CCB(氨氯地平)",
        evidence_level="A", source="ESC高血压指南2018",
    ),
    DrugInteractionRule(
        drug_a="比索洛尔", drug_b="地尔硫䓬", severity="major",
        mechanism="β-blocker+非二氢吡啶CCB双重抑制窦房结",
        clinical_consequence="严重心动过缓、低血压",
        recommendation="密切监测HR/BP，HR<50停用一种",
        evidence_level="A", source="ESC高血压指南2018",
    ),
    
    # ── 降糖 + 其他 ──
    DrugInteractionRule(
        drug_a="二甲双胍", drug_b="碘造影剂", severity="contraindicated",
        mechanism="造影剂诱发肾损伤 → 二甲双胍蓄积 → 乳酸性酸中毒",
        clinical_consequence="致命性乳酸性酸中毒",
        recommendation="增强CT前48h停用二甲双胍，检查后48h复查肾功能正常再恢复",
        evidence_level="A", source="ACR造影剂指南2022",
    ),
    DrugInteractionRule(
        drug_a="胰岛素", drug_b="左氧氟沙星", severity="major",
        mechanism="喹诺酮类药物影响胰岛素分泌和敏感性",
        clinical_consequence="严重低血糖或高血糖",
        recommendation="监测血糖，可能需要调整胰岛素剂量",
        evidence_level="B", source="FDA药物安全通讯",
    ),
    DrugInteractionRule(
        drug_a="格列美脲", drug_b="华法林", severity="major",
        mechanism="磺脲类置换华法林蛋白结合+抑制代谢",
        clinical_consequence="INR升高，出血风险",
        recommendation="监测INR，调整华法林剂量",
        evidence_level="B", source="Micromedex",
    ),
    
    # ── 他汀 + CYP3A4抑制剂 ──
    DrugInteractionRule(
        drug_a="阿托伐他汀", drug_b="克拉霉素", severity="contraindicated",
        mechanism="克拉霉素强CYP3A4抑制剂 → 他汀血药浓度升高5-10倍",
        clinical_consequence="横纹肌溶解症、急性肾衰竭",
        recommendation="抗生素治疗期间暂停他汀，或换用不经CYP3A4代谢的瑞舒伐他汀/普伐他汀",
        evidence_level="A", source="ACC/AHA胆固醇指南2018",
    ),
    DrugInteractionRule(
        drug_a="辛伐他汀", drug_b="胺碘酮", severity="contraindicated",
        mechanism="胺碘酮抑制CYP3A4 → 辛伐他汀浓度显著升高",
        clinical_consequence="横纹肌溶解风险",
        recommendation="辛伐他汀限20mg/d以下，或换用瑞舒伐他汀/普伐他汀",
        evidence_level="A", source="FDA药物安全通讯",
    ),
    DrugInteractionRule(
        drug_a="阿托伐他汀", drug_b="伊曲康唑", severity="contraindicated",
        mechanism="唑类抗真菌药强CYP3A4抑制剂",
        clinical_consequence="横纹肌溶解风险",
        recommendation="暂停他汀或换用非CYP3A4代谢他汀",
        evidence_level="A", source="ACC/AHA胆固醇指南2018",
    ),
    DrugInteractionRule(
        drug_a="辛伐他汀", drug_b="地尔硫䓬", severity="major",
        mechanism="地尔硫䓬中度CYP3A4抑制剂",
        clinical_consequence="肌病风险增加",
        recommendation="辛伐他汀≤20mg/d，监测CK",
        evidence_level="A", source="FDA药物安全通讯",
    ),
    
    # ── 利尿剂 + 其他 ──
    DrugInteractionRule(
        drug_a="呋塞米", drug_b="庆大霉素", severity="major",
        mechanism="袢利尿剂+氨基糖苷双重耳毒性+肾毒性",
        clinical_consequence="不可逆听力损伤、急性肾损伤",
        recommendation="避免联用。必须联用时监测听力+肾功能",
        evidence_level="A", source="中国抗菌药物临床应用指导原则",
    ),
    DrugInteractionRule(
        drug_a="呋塞米", drug_b="布洛芬", severity="major",
        mechanism="NSAID减少肾血流 → 拮抗利尿剂效果 + 肾毒性",
        clinical_consequence="利尿效果减弱、急性肾损伤",
        recommendation="避免联用或严密监测尿量/肾功能",
        evidence_level="B", source="KDIGO AKI指南",
    ),
    DrugInteractionRule(
        drug_a="氢氯噻嗪", drug_b="碳酸锂", severity="major",
        mechanism="噻嗪类减少锂清除 → 血锂浓度升高",
        clinical_consequence="锂中毒(恶心、震颤、共济失调、意识障碍)",
        recommendation="监测血锂浓度，可能需要减量50%",
        evidence_level="A", source="Micromedex",
    ),
    
    # ── 心衰特需 ──
    DrugInteractionRule(
        drug_a="地高辛", drug_b="胺碘酮", severity="major",
        mechanism="胺碘酮抑制P-gp转运 → 地高辛浓度升高50-100%",
        clinical_consequence="地高辛中毒(恶心、视觉异常、心律失常)",
        recommendation="地高辛减量50%，监测地高辛血药浓度",
        evidence_level="A", source="AHA地高辛使用共识",
    ),
    DrugInteractionRule(
        drug_a="地高辛", drug_b="呋塞米", severity="moderate",
        mechanism="呋塞米致低钾 → 心肌对地高辛敏感性增加",
        clinical_consequence="地高辛中毒风险(即使血药浓度正常)",
        recommendation="维持血钾>4.0mmol/L，定期监测心电图",
        evidence_level="B", source="AHA地高辛使用共识",
    ),
    DrugInteractionRule(
        drug_a="沙库巴曲缬沙坦", drug_b="培哚普利", severity="contraindicated",
        mechanism="ARNI+ACEi双重阻断RAAS → 血管性水肿风险",
        clinical_consequence="致命性血管性水肿",
        recommendation="绝对禁止联用。ACEi停药至少36h后才能启动ARNI",
        evidence_level="A", source="ESC心衰指南2021",
    ),
    
    # ── 抗血小板 + PPI ──
    DrugInteractionRule(
        drug_a="氯吡格雷", drug_b="奥美拉唑", severity="major",
        mechanism="奥美拉唑抑制CYP2C19 → 氯吡格雷活性代谢物减少",
        clinical_consequence="抗血小板效果减弱，支架血栓风险增加",
        recommendation="换用对CYP2C19影响小的泮托拉唑，或换用替格瑞洛",
        evidence_level="A", source="FDA药物安全通讯",
    ),
    DrugInteractionRule(
        drug_a="氯吡格雷", drug_b="埃索美拉唑", severity="moderate",
        mechanism="同奥美拉唑，CYP2C19抑制作用较弱",
        clinical_consequence="可能有轻微影响",
        recommendation="首选泮托拉唑。如已联用，可继续但需警惕",
        evidence_level="B", source="ESC DAPT指南2017",
    ),
    
    # ── 抗凝 + 抗血小板 ──
    DrugInteractionRule(
        drug_a="华法林", drug_b="阿司匹林", severity="major",
        mechanism="双重抗凝+抗血小板 → 叠加效应",
        clinical_consequence="出血风险显著增加(颅内出血+消化道出血)",
        recommendation="仅在明确适应证下联用(如机械瓣)，严密监测INR+Hb",
        evidence_level="A", source="ACCP抗栓指南(第10版)",
    ),
    DrugInteractionRule(
        drug_a="利伐沙班", drug_b="阿司匹林", severity="major",
        mechanism="NOAC+抗血小板叠加",
        clinical_consequence="出血风险增加",
        recommendation="仅在ACS/PCI后明确适应证的短期内联用",
        evidence_level="A", source="ESC NSTE-ACS指南2020",
    ),
    DrugInteractionRule(
        drug_a="华法林", drug_b="氯吡格雷", severity="major",
        mechanism="抗凝+抗血小板叠加",
        clinical_consequence="三联抗栓出血风险显著增加",
        recommendation="尽量缩短三联时间(≤1周)，尽早降级",
        evidence_level="A", source="ESC房颤指南2020",
    ),
    
    # ── 其他关键 ──
    DrugInteractionRule(
        drug_a="甲氨蝶呤", drug_b="布洛芬", severity="contraindicated",
        mechanism="NSAID显著减少甲氨蝶呤肾清除",
        clinical_consequence="致命性骨髓抑制、肝肾衰竭",
        recommendation="禁止联用",
        evidence_level="A", source="中国类风湿关节炎诊疗指南",
    ),
    DrugInteractionRule(
        drug_a="碳酸锂", drug_b="布洛芬", severity="major",
        mechanism="NSAID减少锂排泄30-60%",
        clinical_consequence="锂中毒",
        recommendation="监测血锂浓度，调整锂剂量",
        evidence_level="A", source="Micromedex",
    ),
    DrugInteractionRule(
        drug_a="甲巯咪唑", drug_b="华法林", severity="moderate",
        mechanism="甲亢控制后代谢率下降 → 华法林需求量减少",
        clinical_consequence="INR可能升高",
        recommendation="甲亢治疗期间每周监测INR",
        evidence_level="B", source="中国甲亢诊治指南",
    ),
    DrugInteractionRule(
        drug_a="万古霉素", drug_b="呋塞米", severity="moderate",
        mechanism="袢利尿剂可能加重万古霉素肾毒性",
        clinical_consequence="AKI风险增加",
        recommendation="监测万古霉素血药浓度和肾功能",
        evidence_level="B", source="中国万古霉素TDM指南",
    ),
]


# ============================================================================
# 检测函数
# ============================================================================


def detect_interactions(med_list: list[str]) -> list[DrugInteractionRule]:
    """检测药物列表中的相互作用。
    
    Args:
        med_list: 药物名称列表（通用名片段即可，部分匹配）
    
    Returns:
        匹配到的 DrugInteractionRule 列表
    """
    results = []
    med_lower = [m.lower() for m in med_list]
    
    for rule in MEDICATION_INTERACTION_RULES:
        drug_a_found = any(rule.drug_a.lower() in m.lower() for m in med_list)
        drug_b_found = any(rule.drug_b.lower() in m.lower() for m in med_list)
        if drug_a_found and drug_b_found:
            results.append(rule)
    
    return results


def check_allergy_contraindications(
    med_list: list[str],
    allergies: list[str],
) -> list[AllergyContraindication]:
    """检查药物与过敏史的禁忌匹配。
    
    Args:
        med_list: 药物列表
        allergies: 已知过敏原列表
    
    Returns:
        匹配到的过敏禁忌列表
    """
    results = []
    
    # 常见药物-过敏原映射
    allergy_map = {
        "青霉素": ["青霉素类", "阿莫西林", "哌拉西林", "氨苄西林"],
        "头孢菌素": ["头孢", "头孢曲松", "头孢呋辛", "头孢哌酮"],
        "磺胺": ["磺胺", "SMZ", "复方新诺明", "柳氮磺吡啶"],
        "阿司匹林": ["阿司匹林", "NSAID", "布洛芬", "双氯芬酸"],
        "ACEi": ["培哚普利", "卡托普利", "依那普利", "贝那普利", "福辛普利"],
        "碘": ["碘造影剂", "胺碘酮"],
    }
    
    for allergen in allergies:
        allergen_lower = allergen.lower()
        related_drugs = []
        
        for key, drugs in allergy_map.items():
            if key.lower() in allergen_lower or allergen_lower in key.lower():
                related_drugs = drugs
                break
        
        for med in med_list:
            med_lower = med.lower()
            for rd in related_drugs:
                if rd.lower() in med_lower:
                    results.append(AllergyContraindication(
                        medication=med,
                        allergen=allergen,
                        severity="major",
                        recommendation=f"患者已知{allergen}过敏，禁止使用含{rd}成分药物{med}",
                    ))
                    break
    
    return results


# ── 药物-疾病禁忌 ──

class DrugDiseaseRule(BaseModel):
    drug: str
    disease_condition: str
    severity: Literal["contraindicated", "major", "moderate"]
    clinical_consequence: str
    recommendation: str
    evidence_level: str
    source: str


DRUG_DISEASE_RULES: list[DrugDiseaseRule] = [
    DrugDiseaseRule(drug="华法林", disease_condition="肝硬化/严重肝病", severity="contraindicated",
        clinical_consequence="INR不可预测，出血风险极高",
        recommendation="避免使用，考虑低分子肝素", evidence_level="A", source="ACCP抗栓指南"),
    DrugDiseaseRule(drug="二甲双胍", disease_condition="eGFR<30", severity="contraindicated",
        clinical_consequence="乳酸性酸中毒风险",
        recommendation="禁用二甲双胍，换用其他降糖药", evidence_level="A", source="KDIGO CKD指南"),
    DrugDiseaseRule(drug="NSAID", disease_condition="心力衰竭", severity="major",
        clinical_consequence="钠水潴留→心衰恶化",
        recommendation="避免NSAID，首选对乙酰氨基酚", evidence_level="A", source="ESC心衰指南2021"),
    DrugDiseaseRule(drug="NSAID", disease_condition="CKD", severity="contraindicated",
        clinical_consequence="急性肾损伤",
        recommendation="禁用NSAID", evidence_level="A", source="KDIGO CKD指南"),
    DrugDiseaseRule(drug="ACEi", disease_condition="双侧肾动脉狭窄", severity="contraindicated",
        clinical_consequence="急性肾衰竭",
        recommendation="禁用ACEi/ARB", evidence_level="A", source="中国高血压防治指南"),
    DrugDiseaseRule(drug="螺内酯", disease_condition="高钾血症", severity="contraindicated",
        clinical_consequence="致命性高钾血症",
        recommendation="停用螺内酯，纠正高钾后再评估", evidence_level="A", source="ESC心衰指南"),
    DrugDiseaseRule(drug="苯二氮䓬类", disease_condition="COPD/呼吸衰竭", severity="major",
        clinical_consequence="呼吸抑制",
        recommendation="避免使用", evidence_level="B", source="GOLD COPD指南"),
    DrugDiseaseRule(drug="糖皮质激素", disease_condition="未控制的糖尿病", severity="major",
        clinical_consequence="严重高血糖",
        recommendation="加强血糖监测，调整降糖方案", evidence_level="A", source="中国糖尿病指南"),
]


def detect_drug_disease_contraindications(
    med_list: list[str], conditions: list[str], egfr: float | None = None
) -> list[dict]:
    """检测药物-疾病禁忌。"""
    results = []
    for rule in DRUG_DISEASE_RULES:
        drug_matched = any(rule.drug.lower() in m.lower() for m in med_list)
        condition_matched = any(c.lower() in rule.disease_condition.lower() for c in conditions)
        if egfr is not None and "egfr" in rule.disease_condition.lower():
            if "<30" in rule.disease_condition.lower() and egfr < 30:
                condition_matched = True
        if drug_matched and condition_matched:
            results.append({
                "drug": rule.drug, "condition": rule.disease_condition,
                "severity": rule.severity, "consequence": rule.clinical_consequence,
                "recommendation": rule.recommendation, "evidence": rule.evidence_level,
            })
    return results
