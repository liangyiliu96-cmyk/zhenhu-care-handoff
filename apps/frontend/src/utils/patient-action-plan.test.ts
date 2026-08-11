import { describe, expect, it } from 'vitest';

import type { DashboardResponse, RoundsResponse } from '@/types/patient-dashboard';
import { patientActionPlan } from './patient-action-plan';

describe('patient action plan', () => {
  it('keeps deterministic safety work ahead of optional discharge work', () => {
    const dashboard = {
      complication_alerts: ['血压波动需要复评'],
      pending_review_type: 'med_confirm',
      discharge_criteria_status: { all_met: true },
      phase: 'monitoring', discharge_sign_status: '', bridge_status: '',
    } as unknown as DashboardResponse;

    expect(patientActionPlan(dashboard).map((item) => item.target)).toEqual(['monitoring', 'review', 'rounds']);
  });

  it('directs an unreviewed latest SOAP record to the rounds workspace', () => {
    const dashboard = { complication_alerts: [], pending_review_type: '', phase: 'monitoring', discharge_sign_status: '', bridge_status: '' } as unknown as DashboardResponse;
    const rounds = { rounds: [], latest_soap: { round_number: 2, review_status: 'requires_clinician_review' } } as unknown as RoundsResponse;

    expect(patientActionPlan(dashboard, rounds)).toContainEqual(expect.objectContaining({
      target: 'rounds',
      title: '核对最新查房摘要',
      kind: 'review',
      completion: expect.stringContaining('已核对'),
    }));
  });

  it('shows discharge conditions as blockers only after the formal discharge path starts', () => {
    const dashboard = {
      complication_alerts: [], pending_review_type: '', phase: 'discharge', discharge_sign_status: '', bridge_status: '',
      discharge_criteria_status: { all_met: false, details: [{ key: 'medication_titrated', label: '用药方案确认', met: false, category: 'orders', action: '完成用药确认' }] },
    } as unknown as DashboardResponse;

    expect(patientActionPlan(dashboard)).toContainEqual(expect.objectContaining({ key: 'blocker-medication_titrated', target: 'orders', focus: 'medication_titrated' }));
  });

  it('adds a clinical kind and an observable completion condition to safety work', () => {
    const dashboard = {
      complication_alerts: ['持续低血压告警'],
      pending_review_type: '',
      phase: 'monitoring',
      discharge_sign_status: '',
      bridge_status: '',
    } as unknown as DashboardResponse;

    expect(patientActionPlan(dashboard)[0]).toEqual(expect.objectContaining({
      target: 'monitoring',
      kind: 'safety',
      completion: expect.stringContaining('告警'),
    }));
  });
});
