"""药物相互作用规则库测试。"""

from zhenhu.inpatient.agent.medication_rules import (
    detect_interactions, check_allergy_contraindications,
    detect_drug_disease_contraindications, DrugInteractionRule,
    DrugDiseaseRule, DRUG_DISEASE_RULES,
)


def test_detect_warfarin_nsaid():
    r = detect_interactions(["华法林", "布洛芬"])
    assert len(r) == 1
    assert r[0].severity == "contraindicated"


def test_detect_no_interaction():
    r = detect_interactions(["阿莫西林", "对乙酰氨基酚"])
    assert len(r) == 0


def test_detect_clopidogrel_omeprazole():
    r = detect_interactions(["氯吡格雷", "奥美拉唑"])
    assert len(r) == 1
    assert r[0].severity == "major"


def test_detect_multiple_drugs():
    r = detect_interactions(["华法林", "布洛芬", "氯吡格雷", "奥美拉唑"])
    assert len(r) >= 2


def test_empty_med_list():
    assert detect_interactions([]) == []


def test_allergy_penicillin_amoxicillin():
    r = check_allergy_contraindications(["阿莫西林"], ["青霉素过敏"])
    assert len(r) == 1
    assert r[0].severity == "major"


def test_allergy_no_match():
    r = check_allergy_contraindications(["阿莫西林"], ["花粉过敏"])
    assert len(r) == 0


def test_allergy_cephalosporin():
    r = check_allergy_contraindications(["头孢曲松"], ["头孢菌素过敏"])
    assert len(r) == 1


def test_allergy_empty_inputs():
    assert check_allergy_contraindications([], []) == []
    assert check_allergy_contraindications(["阿莫西林"], []) == []


def test_drug_disease_metformin_ckd():
    r = detect_drug_disease_contraindications(["二甲双胍"], ["CKD"], egfr=25)
    assert len(r) >= 1
    assert any(x["drug"] == "二甲双胍" for x in r)


def test_drug_disease_nsaid_heart_failure():
    r = detect_drug_disease_contraindications(["NSAID", "布洛芬"], ["心力衰竭"])
    assert len(r) >= 1


def test_drug_disease_no_match():
    r = detect_drug_disease_contraindications(["阿莫西林"], ["高血压"])
    assert len(r) == 0


def test_drug_disease_rules_count():
    assert len(DRUG_DISEASE_RULES) >= 8


def test_drug_disease_eGFR_threshold():
    r = detect_drug_disease_contraindications(["二甲双胍"], ["糖尿病"], egfr=35)
    assert len(r) == 0  # eGFR > 30, no contraindication
