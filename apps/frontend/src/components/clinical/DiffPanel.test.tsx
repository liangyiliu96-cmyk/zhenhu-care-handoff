// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import DiffPanel from './DiffPanel';

const review = vi.hoisted(() => ({ submitReview: vi.fn() }));
vi.mock('@/services/review-service', () => review);
vi.mock('./EvidencePanel', () => ({ default: () => <div>evidence</div> }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const patient = { patient_id: 'patient-1', name: '测试患者', disease: '心力衰竭', phase: 'review', state_version: 9, items: [] };

function renderPanel(item: Parameters<typeof DiffPanel>[0]['item']) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><DiffPanel patient={patient} item={item} onClose={vi.fn()} onRefresh={vi.fn()} /></QueryClientProvider>);
}

describe('DiffPanel', () => {
  it('renders the admission review payload and submits structured clinical edits', async () => {
    review.submitReview.mockResolvedValue({ status: 'resumed' });
    renderPanel({
      type: 'ddx_confirm', label: '入院诊断确认', review_type: 'doctor_confirm', review_id: 'review-1',
      payload: { chief_complaint: '活动后气促', hpi_narrative: '三天加重', pe_narrative: '双肺湿啰音', ddx_list: [{ diagnosis: '心力衰竭', likelihood: 'high' }] },
    });

    fireEvent.change(screen.getByLabelText('主诉'), { target: { value: '活动后气促伴水肿' } });
    fireEvent.change(screen.getByLabelText('新增诊断'), { target: { value: '肺部感染' } });
    fireEvent.click(screen.getByRole('button', { name: '新增鉴别诊断' }));
    fireEvent.click(screen.getByRole('button', { name: '批准并继续流程' }));

    await waitFor(() => expect(review.submitReview).toHaveBeenCalledWith('patient-1', expect.objectContaining({
      review_type: 'doctor_confirm', decision: 'approved', expected_version: 9,
      edits: expect.objectContaining({
        chief_complaint: '活动后气促伴水肿',
        ddx_edits: expect.arrayContaining([expect.objectContaining({ action: 'add', item: expect.objectContaining({ diagnosis: '肺部感染' }) })]),
      }),
    })));
  });

  it('submits edited handoff items with a discharge signature', async () => {
    review.submitReview.mockResolvedValue({ status: 'resumed' });
    renderPanel({
      type: 'discharge_sign', label: '出院签字', review_type: 'discharge_sign', review_id: 'review-2',
      payload: { handoff_items: [{ type: 'medication', content: '按时服药' }], discharge_criteria_check: { all_met: true } },
    });

    fireEvent.change(screen.getByDisplayValue('按时服药'), { target: { value: '按时服药，不可自行停药' } });
    fireEvent.click(screen.getByRole('button', { name: '签字并提交交接' }));

    await waitFor(() => expect(review.submitReview).toHaveBeenCalledWith('patient-1', expect.objectContaining({
      review_type: 'discharge_sign', decision: 'signed', expected_version: 9,
      handoff_edits: [{ action: 'edit', index: 0, item: { type: 'medication', content: '按时服药，不可自行停药' } }],
    })));
  });
});
