import { describe, expect, it } from 'vitest';

import type { DashboardResponse } from '@/types/patient-dashboard';
import { dischargeBlockerDetails, dischargeWorkflowSteps, operationalDischargeBlockers, reviewTypeLabel } from './discharge-workflow';

describe('discharge workflow projection', () => {
  it('routes backend blockers to the clinical surface that can resolve them', () => {
    expect(dischargeBlockerDetails({ all_met: false, unmet: ['medication_titrated', 'bp_stable_24h'] })).toMatchObject([
      { label: '用药方案已确认并达到出院要求', target: 'orders' },
      { label: '血压稳定达到出院要求', target: 'monitoring' },
    ]);
  });

  it('marks the active review stage without confusing initiation and signature', () => {
    const dashboard = {
      phase: 'discharge', pending_review_type: 'discharge_sign', pending_review_id: 'review-1',
      discharge_sign_status: '', bridge_status: '', handoff_acknowledged: false,
      patient_confirmation_status: '', discharge_criteria_status: { all_met: true },
    } as DashboardResponse;
    const steps = dischargeWorkflowSteps(dashboard);
    expect(steps.find((step) => step.key === 'initiate')?.done).toBe(true);
    expect(steps.find((step) => step.key === 'sign')?.done).toBe(false);
    expect(reviewTypeLabel(dashboard.pending_review_type)).toBe('出院签字审核');
  });

  it('routes post-sign workflow blockers to the discharge preparation page', () => {
    const dashboard = { discharge_blockers: [
      { key: 'follow_up_contact', reason: '未登记随访联系电话', action: '取得授权后补录患者手机联系方式', target: 'contact' },
      { key: 'handoff_acknowledgement', reason: '交接尚未签收', action: '接收方确认交接事项', target: 'handoff' },
    ] } as DashboardResponse;
    expect(operationalDischargeBlockers(dashboard)).toMatchObject([
      { key: 'follow_up_contact', target: 'contact', label: '未登记随访联系电话' },
      { key: 'handoff_acknowledgement', target: 'handoff', label: '交接尚未签收' },
    ]);
  });

  it('does not recreate resolved backend blockers as active work', () => {
    const dashboard = { discharge_blockers: [
      { key: 'follow_up_contact', reason: '未登记随访联系电话', action: '补录联系方式', target: 'contact', status: 'resolved' },
    ] } as DashboardResponse;
    expect(operationalDischargeBlockers(dashboard)).toEqual([]);
  });

  it('marks bridge failures on the handoff workflow step', () => {
    const dashboard = {
      discharge_criteria_status: { all_met: true }, discharge_sign_status: 'signed',
      bridge_status: 'bridge_unavailable', bridge_error: 'bridge_unavailable',
      handoff_acknowledged: false, patient_confirmation_status: '',
    } as DashboardResponse;
    expect(dischargeWorkflowSteps(dashboard).find((step) => step.key === 'handoff')).toMatchObject({
      done: false,
      failed: true,
      description: '协同病例创建失败，需先处理',
    });
  });
});
