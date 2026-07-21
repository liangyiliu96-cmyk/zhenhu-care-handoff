import type { EvidenceGraphRule } from '@/types/evidence-graph';

export const EVIDENCE_RELATION_LABELS: Record<string, string> = {
  HAS_DISCHARGE_CRITERION: '出院标准',
  HAS_MEDICATION_RULE: '用药规则',
  HAS_MONITORING_RULE: '监测重点',
  HAS_CARE_TASK: '护理与随访',
};

const CLINICAL_TEXT: Record<string, string> = {
  high_dose_thiazide: '避免使用大剂量噻嗪类利尿剂',
  systemic_steroids_unless_indicated: '除非有明确适应证，不常规使用全身性糖皮质激素',
  nephrotoxic_drugs_during_recovery: '恢复期避免使用肾毒性药物',
  stop_nephrotoxins: '停用或避免肾毒性药物',
  furosemide_if_fluid_overload: '存在容量超负荷时考虑呋塞米',
  crystalloid_bolus_prn: '必要时给予晶体液快速补液',
  fluid_overload_resolved: '容量超负荷已纠正',
  creatinine_returning_to_baseline: '肌酐回落并接近基线',
  urine_output_gt_0: '尿量保持在可接受水平',
  blood_pressure_stable: '血压保持稳定',
  bp_stable: '血压稳定',
  chest_pain_free_48h: '胸痛已缓解并持续 48 小时无复发',
  dual_antiplatelet_compliance_verified: '已确认双联抗血小板治疗依从性',
  nitroglycerin_response: '评估硝酸甘油治疗反应',
  atorvastatin_rosuvastatin: '阿托伐他汀或瑞舒伐他汀',
  metformin: '二甲双胍',
  basal_bolus: '基础-餐时胰岛素方案',
  insulin_pump: '胰岛素泵治疗',
  basal_insulin: '基础胰岛素',
  glp1_ra: 'GLP-1 受体激动剂',
  sglt2_inhibitor: 'SGLT2 抑制剂',
  acei_arb: 'ACEI 或 ARB 类药物',
  beta_blocker: 'β 受体阻滞剂',
};

export function clinicalRuleText(value: string | undefined): string {
  const normalized = value?.trim() ?? '';
  if (!normalized) return '未提供规则内容';
  return CLINICAL_TEXT[normalized] ?? normalized;
}

export function clinicalRuleKeyLabel(value: string | undefined): string {
  const normalized = value?.trim() ?? '';
  if (!normalized) return '';
  if (normalized === 'contraindicated') return '禁忌或需避免';
  if (normalized === 'monitoring') return '监测项目';
  if (normalized === 'medication') return '用药事项';
  if (normalized === 'followup') return '随访事项';
  return normalized === clinicalRuleText(normalized) ? '' : normalized;
}

export function ruleDisplayText(rule: EvidenceGraphRule): string {
  return clinicalRuleText(rule.content || rule.key);
}
