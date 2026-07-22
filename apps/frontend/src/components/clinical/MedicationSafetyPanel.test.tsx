// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import MedicationSafetyPanel from './MedicationSafetyPanel';

afterEach(cleanup);

describe('MedicationSafetyPanel', () => {
  it('shows external medication evidence as advisory information only', () => {
    render(<MedicationSafetyPanel safety={{
      status: 'complete', conflicts: [], allergy_contraindications: [], gaps: [], duplications: [], warnings: [],
      external_evidence: [{
        drug: 'metoprolol', rxnorm_id: '6918', standard_name: 'metoprolol tartrate',
        warnings: 'Do not stop suddenly.', contraindications: 'Cardiogenic shock.',
        interactions: '', source: 'OpenFDA/RxNorm', status: 'available',
      }],
    }} />);

    expect(screen.getByText('外部药品证据')).toBeTruthy();
    expect(screen.getByText('metoprolol tartrate')).toBeTruthy();
    expect(screen.getByText('OpenFDA/RxNorm')).toBeTruthy();
    expect(screen.getByText('仅供医生复核，不自动生成医嘱。')).toBeTruthy();
  });

  it('does not turn an unrun reconciliation into a false no-interaction statement', () => {
    render(<MedicationSafetyPanel safety={{ status: 'not_run', conflicts: [], allergy_contraindications: [], gaps: [], duplications: [], warnings: [] }} />);

    expect(screen.getByText('尚未完成患者级用药核对，当前不展示“无相互作用”结论。')).toBeTruthy();
    expect(screen.queryByText(/未发现已记录/)).toBeNull();
  });

  it('shows rule evidence and marks model suggestions for clinical review', () => {
    render(<MedicationSafetyPanel safety={{
      status: 'complete',
      conflicts: [
        { drug_pair: '华法林 + 布洛芬', severity: 'contraindicated', mechanism: '出血风险增加', consequence: '消化道出血风险升高', recommendation: '避免联用', evidence: 'A', source: 'ACCP 抗栓指南', model_suggested: false },
        { drug_pair: '模型补充组合', severity: 'moderate', mechanism: '', consequence: '', recommendation: '', evidence: 'LLM', source: '模型补充，需临床复核', model_suggested: true },
      ],
      allergy_contraindications: [{ medication: '阿莫西林', allergen: '青霉素', severity: 'major', recommendation: '避免使用' }],
      gaps: ['缺少出院带药记录'], duplications: [], warnings: [],
    }} />);

    expect(screen.getByText('华法林 + 布洛芬')).toBeTruthy();
    expect(screen.getByText(/依据：ACCP 抗栓指南/)).toBeTruthy();
    expect(screen.getAllByText('需临床复核').length).toBeGreaterThan(0);
    expect(screen.getByText('阿莫西林 / 青霉素')).toBeTruthy();
    expect(screen.getByText('缺少出院带药记录')).toBeTruthy();
  });
});
