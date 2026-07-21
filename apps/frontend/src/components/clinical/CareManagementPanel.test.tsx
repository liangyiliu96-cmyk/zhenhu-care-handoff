// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import CareManagementPanel from './CareManagementPanel';

const service = vi.hoisted(() => ({
  fetchCareManagement: vi.fn(),
  createMedicationOrder: vi.fn(),
  createInvestigationOrder: vi.fn(),
  updateMedicationOrder: vi.fn(),
  updateInvestigationOrder: vi.fn(),
  createMdtRequest: vi.fn(),
  resolveMdtRequest: vi.fn(),
  acknowledgeEducation: vi.fn(),
  createFollowUpTask: vi.fn(),
  updateFollowUpTask: vi.fn(),
}));

vi.mock('@/services/patient-service', () => service);

const emptyCareManagement = {
  patient_id: 'patient-1',
  care_management: { medication_orders: [], mdt_requests: [], education_records: [], follow_up_tasks: [] },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><CareManagementPanel patientId="patient-1" stateVersion={7} /></QueryClientProvider>);
  return { invalidate };
}

async function openMedicationForm() {
  service.fetchCareManagement.mockResolvedValue(emptyCareManagement);
  fireEvent.click(screen.getByRole('button', { name: '展开' }));
  await screen.findByRole('button', { name: '新增医嘱' });
  fireEvent.click(screen.getByRole('button', { name: '新增医嘱' }));
  return within(screen.getByRole('dialog'));
}

function fillMedicationForm(dialog: ReturnType<typeof within>) {
  fireEvent.change(dialog.getByLabelText(/药品名称/), { target: { value: '阿司匹林' } });
  fireEvent.change(dialog.getByLabelText(/剂量/), { target: { value: '100 mg' } });
  fireEvent.change(dialog.getByLabelText(/频次/), { target: { value: 'qd' } });
}

describe('CareManagementPanel', () => {
  it('submits the backend medication payload with the current state version and invalidates dependent queries', async () => {
    service.createMedicationOrder.mockResolvedValue({});
    const { invalidate } = renderPanel();
    const dialog = await openMedicationForm();
    fillMedicationForm(dialog);

    fireEvent.click(dialog.getByRole('button', { name: '新增医嘱' }));

    await waitFor(() => expect(service.createMedicationOrder).toHaveBeenCalledWith('patient-1', {
      medication: '阿司匹林', dose: '100 mg', frequency: 'qd', route: 'PO', indication: '', expected_version: 7,
    }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['patient', 'patient-1'] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['ward'] });
  });

  it('keeps the form open and asks for refresh after a state-version conflict', async () => {
    service.createMedicationOrder.mockRejectedValue(new ApiClientError(409, 'STATE_VERSION_CONFLICT', '状态已变化'));
    renderPanel();
    const dialog = await openMedicationForm();
    fillMedicationForm(dialog);

    fireEvent.click(dialog.getByRole('button', { name: '新增医嘱' }));

    expect(await within(screen.getByRole('dialog')).findByText('患者状态已更新。已刷新当前数据，请核对最新状态后再次确认操作。')).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('creates a manual investigation order through the existing clinical endpoint', async () => {
    service.fetchCareManagement.mockResolvedValue(emptyCareManagement);
    service.createInvestigationOrder.mockResolvedValue({});
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));
    fireEvent.click(await screen.findByRole('button', { name: '开立检查' }));

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.change(dialog.getByLabelText(/检查或检验项目/), { target: { value: '心脏超声' } });
    fireEvent.change(dialog.getByLabelText(/检查原因/), { target: { value: '评估心功能变化' } });
    fireEvent.change(dialog.getByLabelText(/计划时间/), { target: { value: '明日上午' } });
    fireEvent.click(dialog.getByRole('button', { name: '开立检查' }));

    await waitFor(() => expect(service.createInvestigationOrder).toHaveBeenCalledWith('patient-1', {
      test_name: '心脏超声', priority: 'routine', reason: '评估心功能变化', timing: '明日上午', instructions: '', expected_version: 7,
    }));
  });

  it('only exposes an allowed order transition and requires an audit note', async () => {
    service.fetchCareManagement.mockResolvedValue({
      patient_id: 'patient-1',
      care_management: {
        medication_orders: [{ id: 'order-1', medication: '阿司匹林', dose: '100 mg', frequency: 'qd', status: 'draft' }],
        mdt_requests: [], education_records: [], follow_up_tasks: [],
      },
    });
    service.updateMedicationOrder.mockResolvedValue({});
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));
    const activate = await screen.findByRole('button', { name: '激活医嘱' });
    expect(screen.queryByRole('button', { name: '暂停医嘱' })).toBeNull();
    fireEvent.click(activate);

    const dialog = within(screen.getByRole('dialog'));
    expect((dialog.getByRole('button', { name: '确认激活医嘱' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(dialog.getByLabelText(/操作说明/), { target: { value: '医师复核后执行' } });
    fireEvent.click(dialog.getByRole('button', { name: '确认激活医嘱' }));

    await waitFor(() => expect(service.updateMedicationOrder).toHaveBeenCalledWith('patient-1', 'order-1', {
      status: 'active', note: '医师复核后执行', expected_version: 7,
    }));
  });

  it('requires an MDT conclusion summary before resolving a requested MDT record', async () => {
    service.fetchCareManagement.mockResolvedValue({
      patient_id: 'patient-1',
      care_management: {
        medication_orders: [],
        mdt_requests: [{ id: 'mdt-1', reason: '多学科评估', specialties: ['心内科'], status: 'requested' }],
        education_records: [], follow_up_tasks: [],
      },
    });
    service.resolveMdtRequest.mockResolvedValue({});
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));
    fireEvent.click(await screen.findByRole('button', { name: '处理 MDT' }));

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.change(dialog.getByLabelText(/结论摘要/), { target: { value: '建议继续监测并复评' } });
    fireEvent.click(dialog.getByRole('button', { name: '确认处理 MDT 请求' }));

    await waitFor(() => expect(service.resolveMdtRequest).toHaveBeenCalledWith('patient-1', 'mdt-1', {
      decision: 'accepted', summary: '建议继续监测并复评', expected_version: 7,
    }));
  });

  it('sends a documented completion for a pending follow-up task', async () => {
    service.fetchCareManagement.mockResolvedValue({
      patient_id: 'patient-1',
      care_management: {
        medication_orders: [], mdt_requests: [], education_records: [],
        follow_up_tasks: [{ id: 'follow-up-1', title: '血压随访', due_at: '2026-08-01T09:00', status: 'pending' }],
      },
    });
    service.updateFollowUpTask.mockResolvedValue({});
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));
    fireEvent.click(await screen.findByRole('button', { name: '完成' }));

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.change(dialog.getByLabelText(/操作说明/), { target: { value: '已完成电话随访' } });
    fireEvent.click(dialog.getByRole('button', { name: '确认完成随访任务' }));

    await waitFor(() => expect(service.updateFollowUpTask).toHaveBeenCalledWith('patient-1', 'follow-up-1', {
      status: 'completed', note: '已完成电话随访', expected_version: 7,
    }));
  });

  it('shows an approved investigation order and records its completion', async () => {
    service.fetchCareManagement.mockResolvedValue({
      patient_id: 'patient-1',
      care_management: {
        medication_orders: [], mdt_requests: [], education_records: [], follow_up_tasks: [],
        investigation_orders: [{ id: 'investigation-1', test_name: '血钾', priority: 'urgent', reason: '利尿后监测', status: 'ordered' }],
      },
    });
    service.updateInvestigationOrder.mockResolvedValue({});
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));
    fireEvent.click(await screen.findByRole('button', { name: '标记完成' }));

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.change(dialog.getByLabelText(/操作说明/), { target: { value: '检验结果已回报' } });
    fireEvent.click(dialog.getByRole('button', { name: '确认完成检查' }));

    await waitFor(() => expect(service.updateInvestigationOrder).toHaveBeenCalledWith('patient-1', 'investigation-1', {
      status: 'completed', note: '检验结果已回报', expected_version: 7,
    }));
  });

  it('shows an approved assistant education plan as a planned clinical record', async () => {
    service.fetchCareManagement.mockResolvedValue({
      patient_id: 'patient-1',
      care_management: {
        medication_orders: [], mdt_requests: [], education_records: [], follow_up_tasks: [],
        education_plans: [{ id: 'education-plan-1', topic: '起搏器术后宣教', recipient: 'patient', key_points: ['伤口观察', '复诊时间'], status: 'planned' }],
      },
    });
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '展开' }));

    expect(await screen.findByText('起搏器术后宣教')).toBeTruthy();
    expect(screen.getByText('patient · 伤口观察、复诊时间')).toBeTruthy();
  });
});
