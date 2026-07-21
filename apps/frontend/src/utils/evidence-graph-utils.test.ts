import { describe, expect, it } from 'vitest';

import { clinicalRuleKeyLabel, clinicalRuleText, ruleDisplayText } from './evidence-graph-utils';

describe('evidence graph display utilities', () => {
  it('renders internal medication tokens as clinician-readable Chinese', () => {
    expect(clinicalRuleText('high_dose_thiazide')).toBe('避免使用大剂量噻嗪类利尿剂');
    expect(clinicalRuleText('systemic_steroids_unless_indicated')).toBe('除非有明确适应证，不常规使用全身性糖皮质激素');
    expect(clinicalRuleText('basal_bolus')).toBe('基础-餐时胰岛素方案');
  });

  it('keeps authored Chinese rules unchanged', () => {
    expect(clinicalRuleText('掌握血糖自我监测方法')).toBe('掌握血糖自我监测方法');
  });

  it('uses the translated content as the primary rule display', () => {
    expect(ruleDisplayText({ relation: 'HAS_MEDICATION_RULE', labels: [], key: 'contraindicated', content: 'high_dose_thiazide' })).toBe('避免使用大剂量噻嗪类利尿剂');
    expect(clinicalRuleKeyLabel('contraindicated')).toBe('禁忌或需避免');
  });
});
