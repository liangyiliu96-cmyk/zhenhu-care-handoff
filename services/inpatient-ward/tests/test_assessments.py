"""入院评估模型测试。"""

from zhenhu.inpatient.agent.assessments import (
    PainAssessment, NutritionScreening, FallRiskAssessment,
    DVTRiskAssessment, AdmissionAssessments,
    CognitiveScreening, FunctionalAssessment,
    ComprehensiveGeriatricAssessment,
)


def test_pain_mild():
    p = PainAssessment(score=3)
    assert p.severity == "mild"
    assert not p.alert


def test_pain_severe():
    p = PainAssessment(score=8)
    assert p.severity == "severe"
    assert p.alert


def test_nutrition_at_risk():
    n = NutritionScreening(disease_severity=2, nutrition_impairment=1, age_bonus=1)
    assert n.total_score == 4
    assert n.at_risk


def test_fall_high_risk():
    f = FallRiskAssessment(fall_history=True, iv_or_heparin_lock=True, age_ge_70=True)
    assert f.total_score >= 45
    assert f.risk_level == "high"


def test_fall_default_low():
    f = FallRiskAssessment()
    assert f.total_score == 0
    assert f.risk_level == "low"


def test_dvt_high_risk_cancer():
    d = DVTRiskAssessment(active_cancer=True, age_ge_70=True)
    assert d.padua_score >= 4
    assert d.risk_level == "high"
    assert d.needs_prophylaxis


def test_dvt_low_risk():
    d = DVTRiskAssessment()
    assert d.padua_score == 0
    assert d.risk_level == "low"


def test_assessment_alerts():
    a = AdmissionAssessments(
        pain=PainAssessment(score=7),
        fall_risk=FallRiskAssessment(fall_history=True, iv_or_heparin_lock=True, age_ge_70=True),
        dvt_risk=DVTRiskAssessment(active_cancer=True),
    )
    alerts = a.alerts
    assert any("疼痛" in x for x in alerts)
    assert any("跌倒" in x or "Morse" in x for x in alerts)


def test_cognitive_normal():
    c = CognitiveScreening()
    assert c.total_score == 30
    assert c.impairment_level == "normal"


def test_cognitive_severe():
    c = CognitiveScreening(orientation=3, memory=2, attention=1, language=3, visuospatial=0)
    assert c.total_score == 9
    assert c.impairment_level == "severe"


def test_functional_independent():
    f = FunctionalAssessment()
    assert f.adl_score == 100
    assert f.dependency_level == "independent"


def test_cga_applicable():
    cga = ComprehensiveGeriatricAssessment(age=75)
    assert cga.applicable


def test_cga_not_applicable():
    cga = ComprehensiveGeriatricAssessment(age=40)
    assert not cga.applicable
