// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import FollowUpOverviewPanel from './FollowUpOverviewPanel';

afterEach(cleanup);

vi.mock('@/hooks/use-follow-up', () => ({
  useFollowUpOverview: () => ({
    isLoading: false,
    error: null,
    data: {
      summary: { total_patients: 1, pending_follow_ups: 1, overdue_follow_ups: 0, abnormal_feedbacks: 0, high_readmission_risk: 0 },
      patients: [{
        patient_id: 'patient/1',
        name: '测试患者',
        disease: '高血压',
        department: '心内科',
        discharge_status: 'signed',
        follow_up_status: 'pending',
        pending_task_count: 1,
        overdue_task_count: 0,
        abnormal_feedback_count: 0,
        feedback_status: 'unreported',
        readmission_risk: 'low',
        risk_method: 'rule_based_follow_up_priority',
        risk_basis: ['未发现规则升级条件'],
        next_due_at: '2026-08-01T09:00:00+08:00',
        contact: { has_contact: true, follow_up_consent: true, masked_mobile_phone: '138****0000' },
        tasks: [{ id: 'task-1', title: '电话随访', status: 'pending', note: '', is_open: true, is_overdue: false, has_abnormal_feedback: false }],
      }],
    },
    refetch: vi.fn(),
  }),
}));

describe('FollowUpOverviewPanel', () => {
  it('links every follow-up row to the canonical patient coordination section', () => {
    render(<MemoryRouter><FollowUpOverviewPanel /></MemoryRouter>);

    expect(screen.getByRole('link', { name: '进入随访协同' }).getAttribute('href')).toBe('/patient/patient%2F1?section=orders');
  });
});
