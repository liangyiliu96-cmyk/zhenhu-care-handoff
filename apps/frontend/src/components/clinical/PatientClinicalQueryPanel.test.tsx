// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import PatientClinicalQueryPanel from './PatientClinicalQueryPanel';

const patient = vi.hoisted(() => ({ queryPatient: vi.fn() }));
vi.mock('@/services/patient-service', () => patient);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><PatientClinicalQueryPanel patientId="patient-1" /></QueryClientProvider>);
}

describe('PatientClinicalQueryPanel', () => {
  it('sends a preset clinical question and renders its evidence-backed answer', async () => {
    patient.queryPatient.mockResolvedValue({
      patient_id: 'patient-1',
      question: '本轮查房需要重点核对哪些数据？',
      answer: '优先核对血钾、肌酐变化和利尿剂反应。',
      citations: [{ title: '心衰住院管理要点', excerpt: '利尿治疗期间复查肾功能和电解质。' }],
    });
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: '本轮查房需要重点核对哪些数据？' }));

    await waitFor(() => expect(patient.queryPatient).toHaveBeenCalledWith('patient-1', '本轮查房需要重点核对哪些数据？'));
    expect(await screen.findByText('优先核对血钾、肌酐变化和利尿剂反应。')).toBeTruthy();
    expect(screen.getByText('心衰住院管理要点')).toBeTruthy();
  });

  it('submits a manually entered patient-scoped question', async () => {
    patient.queryPatient.mockResolvedValue({ patient_id: 'patient-1', question: '出院阻塞项是什么？', answer: '交接签收尚未完成。', citations: [] });
    renderPanel();

    fireEvent.change(screen.getByRole('textbox', { name: '临床问题' }), { target: { value: ' 出院阻塞项是什么？ ' } });
    fireEvent.click(screen.getByRole('button', { name: '查询患者状态' }));

    await waitFor(() => expect(patient.queryPatient).toHaveBeenCalledWith('patient-1', '出院阻塞项是什么？'));
    expect(await screen.findByText('交接签收尚未完成。')).toBeTruthy();
  });
});
