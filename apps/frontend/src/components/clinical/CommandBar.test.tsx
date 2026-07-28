// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import CommandBar from './CommandBar';
import * as patientService from '@/services/patient-service';

vi.mock('@/services/patient-service', () => ({
  submitDoctorCommand: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('CommandBar', () => {
  it('requires a transfer destination before submitting the doctor command', async () => {
    vi.mocked(patientService.submitDoctorCommand).mockResolvedValue({
      patient_id: 'patient-1', action: 'transfer', status: 'pending_review', phase: 'monitoring', message: 'pending review',
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <CommandBar
          patientId="patient-1"
          stateVersion={7}
          isOnHold={false}
          canStartDischarge={false}
          onOpenDischarge={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '转科' }));

    const dialog = await screen.findByRole('dialog');
    const [destination, reason] = within(dialog).getAllByRole('textbox') as HTMLInputElement[];
    const submit = within(dialog).getByRole('button', { name: '转科' }) as HTMLButtonElement;
    expect(destination.value).toBe('');
    expect(submit.disabled).toBe(true);

    fireEvent.change(destination, { target: { value: 'ICU' } });
    fireEvent.change(reason, { target: { value: '需要进一步监护' } });
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);

    await waitFor(() => expect(patientService.submitDoctorCommand).toHaveBeenCalledWith('patient-1', {
      action: 'transfer',
      target: 'ICU',
      reason: '需要进一步监护',
      expected_version: 7,
    }));
  });
});
