// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import NursingTaskCompletionDialog, { type NursingTaskSelection } from './NursingTaskCompletionDialog';

const service = vi.hoisted(() => ({ completeNursingTask: vi.fn() }));
vi.mock('@/services/nurse-management-service', () => service);

const selection: NursingTaskSelection = {
  patient: {
    patient_id: 'patient-1', state_version: 7, name: '张患者', disease: '心力衰竭', department: '心内科',
    vital_signs_due: true, alert_count: 0, pending_nursing_actions: [], pending_medications: [],
  },
  task: {
    task_key: 'vital_signs:abc', task_type: 'vital_signs', title: '测量并记录生命体征',
    description: '患者体征已到复测时间。', priority: 'normal',
  },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const onClose = vi.fn();
  render(<QueryClientProvider client={client}><NursingTaskCompletionDialog selection={selection} onClose={onClose} /></QueryClientProvider>);
  return { invalidate, onClose };
}

describe('NursingTaskCompletionDialog', () => {
  it('submits the server task key and state version, then refreshes downstream views', async () => {
    service.completeNursingTask.mockResolvedValue({ completion: { id: 'done-1' }, state_version: 8 });
    const { invalidate, onClose } = renderDialog();
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.change(dialog.getByLabelText('执行备注'), { target: { value: '已完成床旁测量' } });
    fireEvent.click(dialog.getByRole('button', { name: '确认完成' }));

    await waitFor(() => expect(service.completeNursingTask).toHaveBeenCalled());
    const [patientId, payload, idempotencyKey] = service.completeNursingTask.mock.calls[0];
    expect(patientId).toBe('patient-1');
    expect(payload).toEqual({ task_type: 'vital_signs', task_key: 'vital_signs:abc', note: '已完成床旁测量', expected_version: 7 });
    expect(idempotencyKey).toMatch(/^nursing-task:patient-1:vital_signs:abc:/);
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['nurse'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['ward'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['patient', 'patient-1'] });
    expect(onClose).toHaveBeenCalled();
  });

  it('keeps the dialog open and refreshes tasks after a conflict', async () => {
    service.completeNursingTask.mockRejectedValue(new ApiClientError(409, 'STATE_VERSION_CONFLICT', '护理任务已经完成'));
    const { invalidate, onClose } = renderDialog();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认完成' }));

    expect(await screen.findByText('护理任务已经完成')).toBeTruthy();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['nurse', 'tasks'] });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
});
