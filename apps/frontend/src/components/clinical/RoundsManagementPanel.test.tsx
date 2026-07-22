// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
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
});
