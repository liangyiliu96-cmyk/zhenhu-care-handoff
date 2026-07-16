"""入院标准临床评估工具 —— P2补全: 疼痛/营养/跌倒/DVT。

M4: 疼痛NRS, M5: 营养NRS2002, M6: 跌倒Morse, M7: DVT Padua/Caprini。
全部Pydantic模型，可独立导入和测试。
"""

from __future__ import annotations
from pydantic import BaseModel, Field


# ── M4: 疼痛评估 (NRS) ──

class PainAssessment(BaseModel):
    """疼痛数字评分法 NRS 0-10。

    0=无痛, 1-3=轻度, 4-6=中度, 7-10=重度。
    JCI标准: 第5生命体征, 所有住院患者均应评估。
    """
    score: int = Field(..., ge=0, le=10, description="NRS疼痛评分")
    location: str | None = Field(None, description="疼痛部位")
    character: str | None = Field(None, description="疼痛性质(钝痛/刺痛/绞痛等)")
    reassess_interval_hours: int = Field(4, description="复评间隔(小时)")

    @property
    def severity(self) -> str:
        if self.score >= 7:
            return "severe"
        elif self.score >= 4:
            return "moderate"
        elif self.score >= 1:
            return "mild"
        return "none"

    @property
    def alert(self) -> bool:
        return self.score >= 7


# ── M5: 营养筛查 (NRS2002) ──

class NutritionScreening(BaseModel):
    """营养风险筛查 NRS2002。

    总评分 = 疾病严重度(0-3) + 营养状况(0-3) + 年龄(≥70岁+1)。
    ≥3分=有营养风险，需营养干预。ESPEN指南推荐。
    """
    disease_severity: int = Field(0, ge=0, le=3, description="疾病严重度评分")
    nutrition_impairment: int = Field(0, ge=0, le=3, description="营养状况受损评分")
    age_bonus: int = Field(0, ge=0, le=1, description="年龄加分(≥70岁=1)")

    @property
    def total_score(self) -> int:
        return self.disease_severity + self.nutrition_impairment + self.age_bonus

    @property
    def at_risk(self) -> bool:
        return self.total_score >= 3

    @property
    def needs_intervention(self) -> str:
        if self.total_score >= 5:
            return "urgent_nutrition_support"
        elif self.total_score >= 3:
            return "nutrition_plan_required"
        return "routine_monitoring"


# ── M6: 跌倒风险评估 (Morse) ──

class FallRiskAssessment(BaseModel):
    """Morse跌倒风险评估量表。

    <25=低风险, 25-45=中风险, >45=高风险。
    中国医院协会患者安全目标(2022): 所有住院患者均应评估。
    年龄≥70和行动受限通过secondary_diagnosis/ambulatory_aid映射到Morse计分。
    """
    fall_history: bool = Field(False, description="近3月跌倒史(有=25)")
    secondary_diagnosis: bool = Field(False, description="≥2个医疗诊断(有=15)")
    ambulatory_aid: str = Field("none", description="辅助行走: none/bedrest=0, cane=15, furniture=30")
    iv_or_heparin_lock: bool = Field(False, description="静脉留置/肝素锁(有=20)")
    gait: str = Field("normal", description="步态: normal=0, weak=10, impaired=20")
    mental_status: str = Field("oriented", description="精神状态: oriented=0, overestimates=15")
    # 便捷字段——自动映射到Morse计分项
    age_ge_70: bool = Field(False, description="年龄≥70(自动纳入secondary_diagnosis计分)")
    reduced_mobility: bool = Field(False, description="行动受限(自动设ambulatory_aid=furniture)")

    def _effective_secondary_diagnosis(self) -> bool:
        """年龄≥70视为额外共病风险，自动计入secondary_diagnosis。"""
        return self.secondary_diagnosis or self.age_ge_70

    def _effective_ambulatory_aid(self) -> str:
        """行动受限自动映射为扶家具行走。"""
        if self.reduced_mobility and self.ambulatory_aid == "none":
            return "furniture"
        return self.ambulatory_aid

    @property
    def total_score(self) -> int:
        score = 0
        if self.fall_history:
            score += 25
        if self._effective_secondary_diagnosis():
            score += 15
        amb_map = {"none": 0, "bedrest": 0, "cane": 15, "furniture": 30}
        score += amb_map.get(self._effective_ambulatory_aid(), 0)
        if self.iv_or_heparin_lock:
            score += 20
        gait_map = {"normal": 0, "weak": 10, "impaired": 20}
        score += gait_map.get(self.gait, 0)
        if self.mental_status == "overestimates":
            score += 15
        return score

    @property
    def risk_level(self) -> str:
        s = self.total_score
        if s > 45:
            return "high"
        elif s >= 25:
            return "medium"
        return "low"


# ── M7: DVT风险评估 ──

class DVTRiskAssessment(BaseModel):
    """深静脉血栓风险评估。

    内科患者: Padua评分(≥4=高危，需药物预防)。
    外科患者: Caprini评分(≥5=高危)。
    ACCP指南: 所有住院患者均应评估VTE风险。
    """
    patient_type: str = Field("medical", description="medical=内科(Padua), surgical=外科(Caprini)")
    # Padua 评分项
    active_cancer: bool = False          # +3
    previous_vte: bool = False           # +3
    reduced_mobility: bool = False       # +3
    thrombophilia: bool = False          # +3
    recent_trauma_surgery: bool = False  # +2
    age_ge_70: bool = False              # +1
    heart_resp_failure: bool = False     # +1
    acute_infection: bool = False        # +1
    obesity_bmi_ge_30: bool = False      # +1
    hormonal_treatment: bool = False     # +1

    @property
    def padua_score(self) -> int:
        score = 0
        if self.active_cancer: score += 3
        if self.previous_vte: score += 3
        if self.reduced_mobility: score += 3
        if self.thrombophilia: score += 3
        if self.recent_trauma_surgery: score += 2
        if self.age_ge_70: score += 1
        if self.heart_resp_failure: score += 1
        if self.acute_infection: score += 1
        if self.obesity_bmi_ge_30: score += 1
        if self.hormonal_treatment: score += 1
        return score

    @property
    def risk_level(self) -> str:
        s = self.padua_score
        if s >= 4:
            return "high"
        elif s >= 2:
            return "medium"
        return "low"

    @property
    def needs_prophylaxis(self) -> bool:
        return self.risk_level == "high"


# ── 综合评估汇总 ──

class AdmissionAssessments(BaseModel):
    """入院综合评估结果。"""
    pain: PainAssessment | None = None
    nutrition: NutritionScreening | None = None
    fall_risk: FallRiskAssessment | None = None
    dvt_risk: DVTRiskAssessment | None = None
    allergies: list[str] = Field(default_factory=list)

    @property
    def alerts(self) -> list[str]:
        result = []
        if self.pain and self.pain.alert:
            result.append(f"疼痛评分{self.pain.score}分，需镇痛干预")
        if self.nutrition and self.nutrition.at_risk:
            result.append(f"NRS2002={self.nutrition.total_score}分，需营养干预")
        if self.fall_risk and self.fall_risk.risk_level == "high":
            result.append(f"Morse={self.fall_risk.total_score}分，高风险防跌倒")
        if self.dvt_risk and self.dvt_risk.needs_prophylaxis:
            result.append(f"{'Padua' if self.dvt_risk.patient_type=='medical' else 'Caprini'}={self.dvt_risk.padua_score}分，需VTE预防")
        return result
