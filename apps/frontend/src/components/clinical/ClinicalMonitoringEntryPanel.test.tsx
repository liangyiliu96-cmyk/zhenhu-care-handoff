// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ClinicalMonitoringEntryPanel from './ClinicalMonitoringEntryPanel';

const patient = vi.hoisted(() => ({ reportVitalSigns: vi.fn(), reportLabResult: vi.fn() }));
vi.mock('@/services/patient-service', () => patient);

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ClinicalMonitoringEntryPanel patientId="patient-1" stateVersion={12} /></QueryClientProvider>);
}

describe('ClinicalMonitoringEntryPanel', () => {
  it('submits canonical vital signs with the patient state version', async () => {
    patient.reportVitalSigns.mockResolvedValue({});
    renderPanel();
    fireEvent.change(screen.getByLabelText('收缩压'), { target: { value: '128' } });
    fireEvent.change(screen.getByLabelText('舒张压'), { target: { value: '76' } });
    fireEvent.change(screen.getByLabelText('心率'), { target: { value: '72' } });
    fireEvent.change(screen.getByLabelText('SpO₂'), { target: { value: '98' } });
    fireEvent.click(screen.getByRole('button', { name: '记录体征' }));

    await waitFor(() => expect(patient.reportVitalSigns).toHaveBeenCalledWith('patient-1', expect.objectContaining({
      blood_pressure: '128/76', systolic_mmhg: 128, diastolic_mmhg: 76, heart_rate: 72, spo2: 98, expected_version: 12,
    })));
  });

  it('submits a lab result through the canonical monitoring endpoint', async () => {
    patient.reportLabResult.mockResolvedValue({ pending_review: true });
    renderPanel();
    fireEvent.click(screen.getByRole('tab', { name: '检验结果' }));
    fireEvent.change(screen.getByLabelText('检验项目'), { target: { value: '钾' } });
    fireEvent.change(screen.getByLabelText('结果'), { target: { value: '5.8' } });
    fireEvent.change(screen.getByLabelText('单位'), { target: { value: 'mmol/L' } });
    fireEvent.click(screen.getByRole('button', { name: '记录检验' }));

    await waitFor(() => expect(patient.reportLabResult).toHaveBeenCalledWith('patient-1', {
      name: '钾', value: '5.8', unit: 'mmol/L', expected_version: 12,
    }));
    expect(await screen.findByText('数据已记录，并触发新的医生审核待办。')).toBeTruthy();
  });
});
