// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import DischargeEducationPanel from './DischargeEducationPanel';

const education = vi.hoisted(() => ({ fetchEducationResources: vi.fn() }));
const patient = vi.hoisted(() => ({ acknowledgeEducation: vi.fn(), fetchPatientDashboard: vi.fn() }));

vi.mock('@/services/education-service', () => education);
vi.mock('@/services/patient-service', () => patient);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><DischargeEducationPanel patientId="patient-1" stateVersion={9} disease="心力衰竭" /></QueryClientProvider>);
}

describe('DischargeEducationPanel', () => {
  it('records completed education against the current patient state version', async () => {
    education.fetchEducationResources.mockResolvedValue({ query: 'query', layer: 'L9', count: 1, results: [{ topic: '心力衰竭限钠指导', text: '每日控制钠盐摄入', source: '心衰患者教育' }] });
    patient.fetchPatientDashboard.mockResolvedValue({ state_version: 12 });
    patient.acknowledgeEducation.mockResolvedValue({});
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: '记录已宣教' }));
    fireEvent.change(screen.getByLabelText('回授摘要'), { target: { value: '患者可复述每日限钠要求' } });
    fireEvent.click(screen.getByRole('button', { name: '确认记录' }));

    await waitFor(() => expect(patient.acknowledgeEducation).toHaveBeenCalledWith('patient-1', {
      topic: '心力衰竭限钠指导', recipient: 'patient', teach_back: '患者可复述每日限钠要求', expected_version: 12,
    }));
  });

  it('shows an explicit retrieval failure instead of invented education content', async () => {
    education.fetchEducationResources.mockRejectedValue(new Error('network unavailable'));
    renderPanel();

    expect(await screen.findByText('患者教育资料暂时无法加载，请在资料恢复后完成宣教。')).toBeTruthy();
    expect(screen.queryByText('每日控制钠盐摄入')).toBeNull();
  });

  it('opens the teach-back record directly when the discharge flow requests it', async () => {
    education.fetchEducationResources.mockResolvedValue({ query: 'query', layer: 'L9', count: 0, results: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><DischargeEducationPanel patientId="patient-1" stateVersion={9} disease="心力衰竭" openRecordRequest={1} /></QueryClientProvider>);

    expect(await screen.findByRole('heading', { name: '记录已完成的宣教' })).toBeTruthy();
    expect((screen.getByLabelText('宣教主题') as HTMLInputElement).value).toBe('心力衰竭患者教育与回授');
  });
});
