// @vitest-environment jsdom

import { afterEach, expect, it, vi } from 'vitest';
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

it('filters unrelated RAG education and still records a real teach-back', async () => {
  education.fetchEducationResources.mockResolvedValue({
    query: 'query',
    layer: 'L9',
    count: 1,
    results: [{ topic: 'unrelated education', text: 'unrelated content', source: 'patient_education' }],
  });
  patient.fetchPatientDashboard.mockResolvedValue({ state_version: 10 });
  patient.acknowledgeEducation.mockResolvedValue({});
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><DischargeEducationPanel patientId="patient-1" stateVersion={9} disease="heart failure" /></QueryClientProvider>);

  fireEvent.click(await screen.findByRole('button', { name: '记录本次宣教与回授' }));
  expect(screen.queryByText('unrelated education')).toBeNull();
  fireEvent.change(screen.getByLabelText('回授摘要'), { target: { value: 'Patient repeated daily weight and warning signs.' } });
  fireEvent.click(screen.getByRole('button', { name: '确认记录' }));

  await waitFor(() => expect(patient.acknowledgeEducation).toHaveBeenCalledWith('patient-1', {
    topic: 'heart failure患者教育与回授',
    recipient: 'patient',
    teach_back: 'Patient repeated daily weight and warning signs.',
    expected_version: 10,
  }));
});

it('shows the exact disease-scoped L9 resource even when its title uses a shorter alias', async () => {
  education.fetchEducationResources.mockResolvedValue({
    query: 'query',
    layer: 'L9',
    count: 1,
    results: [{ topic: '心衰患者自我管理', text: '每日晨起称重并记录。', source: 'patient_education', disease_id: 'heart_failure' }],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><DischargeEducationPanel patientId="patient-1" stateVersion={9} disease="心力衰竭" diseaseId="heart_failure" /></QueryClientProvider>);

  expect(await screen.findByText('心衰患者自我管理')).toBeTruthy();
  expect(screen.getByText('每日晨起称重并记录。')).toBeTruthy();
});
