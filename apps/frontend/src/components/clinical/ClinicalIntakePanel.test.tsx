// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ClinicalIntakePanel from './ClinicalIntakePanel';

const service = vi.hoisted(() => ({ recordHistory: vi.fn(), recordPhysicalExam: vi.fn() }));
vi.mock('@/services/patient-service', () => service);

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('ClinicalIntakePanel', () => {
  it('shows pre-round history gaps as non-blocking prompts in the history editor', () => {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <ClinicalIntakePanel
          patientId="patient-1"
          stateVersion={7}
          historyGaps={[{ field: 'allergies', label: '过敏史', status: 'needs_input', prompt: '请补充既往药物或食物过敏史。' }]}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '录入病史' }));

    expect(screen.getByText('建议补充病史')).toBeTruthy();
    expect(screen.getByText('待补：过敏史')).toBeTruthy();
    expect(screen.getByText('请补充既往药物或食物过敏史。')).toBeTruthy();
    expect(screen.queryByText('过敏史已确认')).toBeNull();
  });
});
