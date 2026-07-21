import { describe, expect, it } from 'vitest';

import { clinicalMetricLabel, labTrendMetrics, medicationDetail } from './patient-detail-utils';

describe('patient detail presentation adapters', () => {
  it('keeps only backend-provided medication fields in a readable adjustment row', () => {
    expect(medicationDetail({ medication: '阿司匹林', dose: '100 mg', frequency: 'qd', route: 'PO', indication: '二级预防', status: 'draft' })).toEqual({
      name: '阿司匹林',
      schedule: '100 mg · qd · PO',
      context: '二级预防',
      metadata: 'draft',
    });
  });

  it('sorts lab metrics by observed abnormal count without inventing timestamps', () => {
    const metrics = labTrendMetrics({
      patient_id: 'patient-1', total_labs: 3,
      lab_trends: {
        钾: { unit: 'mmol/L', ref_range: '3.5-5.5', latest: 4.1, min: 3.2, max: 4.1, abnormal_count: 1, total_count: 2, values: [{ index: 0, value: 3.2, is_abnormal: true }, { index: 1, value: 4.1, is_abnormal: false }] },
        肌酐: { unit: 'umol/L', ref_range: '44-133', latest: 160, min: 160, max: 160, abnormal_count: 1, total_count: 1, values: [{ index: 2, value: 160, is_abnormal: true }] },
      },
    });

    expect(metrics.map((metric) => metric.name)).toEqual(['肌酐', '钾']);
    expect(metrics[1].values).toEqual([{ index: 0, value: 3.2, isAbnormal: true }, { index: 1, value: 4.1, isAbnormal: false }]);
  });

  it('localizes common backend lab identifiers', () => {
    expect(clinicalMetricLabel('creatinine')).toBe('肌酐');
    expect(clinicalMetricLabel('potassium')).toBe('血钾');
  });
});
