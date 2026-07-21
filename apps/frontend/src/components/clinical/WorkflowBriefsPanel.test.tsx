// @vitest-environment jsdom

import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import WorkflowBriefsPanel from './WorkflowBriefsPanel';

const service = vi.hoisted(() => ({
  fetchWorkflowBriefs: vi.fn(),
  generateWorkflowBrief: vi.fn(),
}));

vi.mock('@/services/patient-service', () => service);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it('refreshes the state version before generating a nursing follow-up draft', async () => {
  service.fetchWorkflowBriefs
    .mockResolvedValueOnce({ patient_id: 'patient-1', state_version: 7, briefs: {} })
    .mockResolvedValueOnce({ patient_id: 'patient-1', state_version: 9, briefs: {} })
    .mockResolvedValue({ patient_id: 'patient-1', state_version: 10, briefs: {} });
  service.generateWorkflowBrief.mockResolvedValue({ patient_id: 'patient-1', state_version: 8, brief: { kind: 'follow_up' } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

  render(<QueryClientProvider client={client}><WorkflowBriefsPanel patientId="patient-1" stateVersion={3} generatableKinds={['follow_up']} /></QueryClientProvider>);

  expect(await screen.findByText('随访脚本')).toBeTruthy();
  expect(screen.getByRole('button', { name: '生成随访脚本' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '生成MDT 会前简报' })).toBeNull();
  expect(screen.queryByRole('button', { name: '生成转科交接' })).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: '生成随访脚本' }));
  await waitFor(() => expect(service.generateWorkflowBrief).toHaveBeenCalledWith('patient-1', 'follow_up', 9));
});
