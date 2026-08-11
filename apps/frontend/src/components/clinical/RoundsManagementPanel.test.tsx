// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import RoundsManagementPanel from './RoundsManagementPanel';

const service = vi.hoisted(() => ({
  editPatientRound: vi.fn(),
  generatePatientRound: vi.fn(),
  generateProgressNoteDraft: vi.fn(),
  reviewPatientRound: vi.fn(),
}));

vi.mock('@/services/patient-service', () => service);

afterEach(cleanup);

describe('RoundsManagementPanel', () => {
  it('keeps the pre-round brief visible before the first round exists', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <RoundsManagementPanel
          patientId="patient-1"
          stateVersion={5}
          loading={false}
          rounds={{ patient_id: 'patient-1', round_count: 0, total: 0, rounds: [], latest_soap: {} }}
          preRoundBrief={{
            patient_id: 'patient-1',
            state_version: 5,
            attention_items: [],
            history_gaps: [{ field: 'allergies', label: '过敏史', status: 'needs_input', prompt: '请补充过敏史。' }],
          }}
          onOpenMonitoring={vi.fn()}
          onOpenOrders={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText('查房前预读')).toBeTruthy();
    expect(screen.getByText('尚未生成查房摘要')).toBeTruthy();
    expect(screen.getByRole('button', { name: '生成首次查房摘要' })).toBeTruthy();
  });

  it('shows the source facts and missing sections before a progress draft is applied', async () => {
    service.generateProgressNoteDraft.mockResolvedValueOnce({
      patient_id: 'patient-1',
      state_version: 5,
      generation_source: 'rule_based_fact_draft',
      write_back: 'requires_doctor_edit_and_existing_round_review',
      sections: {
        subjective: { text: '主诉：胸闷', status: 'draft', facts: [{ source_type: 'history', field: 'chief_complaint', value: '胸闷' }] },
        objective: { text: '心率82次/分', status: 'draft', facts: [{ source_type: 'vital_sign', field: 'heart_rate', value: 82 }] },
        assessment: { text: '待医生补充', status: 'needs_input', facts: [] },
        plan: { text: '待医生补充', status: 'needs_input', facts: [] },
      },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <RoundsManagementPanel
          patientId="patient-1"
          stateVersion={5}
          loading={false}
          rounds={{ patient_id: 'patient-1', round_count: 1, total: 1, rounds: [{ round_number: 1, review_status: 'reviewed' }], latest_soap: { round_number: 1, review_status: 'reviewed' } }}
          preRoundBrief={{ patient_id: 'patient-1', state_version: 5, attention_items: [], history_gaps: [] }}
          onOpenMonitoring={vi.fn()}
          onOpenOrders={vi.fn()}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '生成增量病程草稿' }));

    await waitFor(() => expect(screen.getByText('来源事实 2 条')).toBeTruthy());
    expect(screen.getByText('仍需医生补充 2 个部分')).toBeTruthy();
    expect(screen.getByText('来源：病史 · 主诉：胸闷')).toBeTruthy();
    expect(screen.getByText('来源：体征 · 心率：82')).toBeTruthy();
    expect(screen.getByText('评估和计划不会被自动填写')).toBeTruthy();
  });
});
