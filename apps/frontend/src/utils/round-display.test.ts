import { describe, expect, it } from 'vitest';

import { clinicalPhaseLabel, formatRoundValue, roundGenerationLabel, roundSectionRows } from './round-display';

describe('round display projection', () => {
  it('translates SOAP fields and clinical values without exposing internal keys', () => {
    expect(roundSectionRows('assessment', { stability: 'stable', response_to_treatment: '症状改善' })).toEqual([
      { key: 'stability', label: '病情稳定性', value: '稳定' },
      { key: 'response_to_treatment', label: '治疗反应', value: '症状改善' },
    ]);
    expect(formatRoundValue({ heart_rate: 82, spo2: 97 })).toBe('心率：82；血氧饱和度：97');
  });

  it('uses clinician-facing labels for decisions and generation source', () => {
    expect(formatRoundValue(true, 'consider_discharge')).toBe('可进入出院条件评估');
    expect(roundGenerationLabel({ generation_source: 'llm_assisted' })).toBe('Agent + LLM 辅助生成');
    expect(clinicalPhaseLabel('discharge')).toBe('出院准备');
  });
});
