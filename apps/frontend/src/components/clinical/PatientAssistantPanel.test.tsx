// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import PatientAssistantPanel from './PatientAssistantPanel';

const service = vi.hoisted(() => ({
  fetchAssistantQuickQuestions: vi.fn(),
  fetchAssistantSessions: vi.fn().mockResolvedValue({ sessions: [] }),
  fetchAssistantSession: vi.fn(),
  resetAssistantSession: vi.fn(),
  streamAssistantChat: vi.fn(),
  fetchAssistantActionDrafts: vi.fn().mockResolvedValue({ patient_id: 'patient-1', state_version: 7, drafts: [] }),
  generateAssistantActionDrafts: vi.fn(),
  updateAssistantActionDraft: vi.fn(),
  decideAssistantActionDraft: vi.fn(),
}));

vi.mock('@/services/assistant-service', () => service);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel(patientId = 'patient-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><PatientAssistantPanel patientId={patientId} /></QueryClientProvider>);
}

async function ask(question: string) {
  fireEvent.change(screen.getByRole('textbox', { name: '向查房助手提问' }), { target: { value: question } });
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
}

describe('PatientAssistantPanel', () => {
  it('binds the conversation to the current patient and drops the session after a patient switch', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.streamAssistantChat.mockImplementation(async (_request: unknown, onEvent: (event: { type: string; sessionId?: string; token?: string; sources?: string[]; citations?: unknown[] }) => void) => {
      onEvent({ type: 'token', token: '建议复查' });
      onEvent({ type: 'complete', sessionId: 'session-1', sources: ['指南'], citations: [] });
    });
    const view = renderPanel();
    fireEvent.click(screen.getByLabelText('展开查房助手'));

    await ask('第一问');
    await waitFor(() => expect(service.streamAssistantChat).toHaveBeenNthCalledWith(
      1,
      { message: '第一问', assistantMode: 'doctor', patientId: 'patient-1', sessionId: undefined, publicAccess: false },
      expect.any(Function),
      expect.any(AbortSignal),
    ));
    await waitFor(() => expect(screen.getByText('建议复查')).toBeTruthy());

    await ask('第二问');
    await waitFor(() => expect(service.streamAssistantChat).toHaveBeenNthCalledWith(
      2,
      { message: '第二问', assistantMode: 'doctor', patientId: 'patient-1', sessionId: 'session-1', publicAccess: false },
      expect.any(Function),
      expect.any(AbortSignal),
    ));

    view.rerender(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PatientAssistantPanel patientId="patient-2" /></QueryClientProvider>);
    await waitFor(() => expect(screen.queryByText('建议复查')).toBeNull());
    await ask('新患者问题');
    await waitFor(() => expect(service.streamAssistantChat).toHaveBeenNthCalledWith(
      3,
      { message: '新患者问题', assistantMode: 'doctor', patientId: 'patient-2', sessionId: undefined, publicAccess: false },
      expect.any(Function),
      expect.any(AbortSignal),
    ));
  });

  it('removes an empty assistant draft when generation is cancelled before any token arrives', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.streamAssistantChat.mockImplementation((_request: unknown, _onEvent: unknown, signal: AbortSignal) => new Promise((_, reject) => {
      signal.addEventListener('abort', () => reject(Object.assign(new Error('cancelled'), { name: 'AbortError' })));
    }));
    renderPanel();
    fireEvent.click(screen.getByLabelText('展开查房助手'));

    await ask('取消前的问题');
    await waitFor(() => expect(screen.getByRole('button', { name: '停止生成' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '停止生成' }));

    await waitFor(() => expect(screen.queryByText('未返回文本内容')).toBeNull());
    expect(screen.getByText('取消前的问题')).toBeTruthy();
  });

  it('starts a new session when switching assistant modes', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.streamAssistantChat.mockImplementation(async (_request: unknown, onEvent: (event: { type: string; sessionId?: string; token?: string; sources?: string[]; citations?: unknown[] }) => void) => {
      onEvent({ type: 'token', token: '已核对' });
      onEvent({ type: 'complete', sessionId: 'mode-session', sources: [], citations: [] });
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><PatientAssistantPanel patientId="patient-1" assistantMode="doctor" availableModes={['doctor', 'pharmacist']} defaultOpen /></QueryClientProvider>);

    fireEvent.click(screen.getByRole('button', { name: '用药' }));
    fireEvent.change(screen.getByRole('textbox', { name: '向用药助手提问' }), { target: { value: '核对相互作用' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));

    await waitFor(() => expect(service.streamAssistantChat).toHaveBeenCalledWith(
      { message: '核对相互作用', assistantMode: 'pharmacist', patientId: 'patient-1', sessionId: undefined, publicAccess: false },
      expect.any(Function),
      expect.any(AbortSignal),
    ));
  });

  it('converts a bound assistant reply into a server-side action draft', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.streamAssistantChat.mockImplementation(async (_request: unknown, onEvent: (event: { type: string; sessionId?: string; token?: string; sources?: string[]; citations?: unknown[] }) => void) => {
      onEvent({ type: 'token', token: '建议今天复查血钾。' });
      onEvent({ type: 'complete', sessionId: 'draft-session', sources: ['指南'], citations: [{ title: '监测指南' }] });
    });
    service.generateAssistantActionDrafts.mockResolvedValue({ patient_id: 'patient-1', state_version: 8, drafts: [{ id: 'draft-1' }] });
    renderPanel();
    fireEvent.click(screen.getByLabelText('展开查房助手'));

    await ask('下一步做什么');
    fireEvent.click(await screen.findByRole('button', { name: '转为操作草稿' }));

    await waitFor(() => expect(service.generateAssistantActionDrafts).toHaveBeenCalledWith('patient-1', {
      session_id: 'draft-session',
      source_text: '建议今天复查血钾。',
      citations: [{ title: '监测指南' }],
      expected_version: 7,
    }));
    expect(await screen.findByText('已生成 1 条待医生审核的操作草稿。')).toBeTruthy();
  });

  it('explains that a timed-out draft conversion did not execute any clinical action', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.streamAssistantChat.mockImplementation(async (_request: unknown, onEvent: (event: { type: string; sessionId?: string; token?: string; sources?: string[]; citations?: unknown[] }) => void) => {
      onEvent({ type: 'token', token: '建议复查血钾。' });
      onEvent({ type: 'complete', sessionId: 'timeout-session', sources: [], citations: [] });
    });
    service.generateAssistantActionDrafts.mockRejectedValue(new ApiClientError(0, 'TIMEOUT', '请求超时'));
    renderPanel();
    fireEvent.click(screen.getByLabelText('展开查房助手'));

    await ask('下一步做什么？');
    fireEvent.click(await screen.findByRole('button', { name: '转为操作草稿' }));

    expect(await screen.findByText('草稿结构化超过时限，助手原始回答未被执行；可再次转换或改用手工临床操作。')).toBeTruthy();
  });

  it('requires an explicit doctor comment before approving and executing a draft', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.fetchAssistantActionDrafts.mockResolvedValue({
      patient_id: 'patient-1',
      state_version: 11,
      drafts: [{
        id: 'draft-investigation', draft_type: 'investigation_order', status: 'pending',
        payload: { test_name: '血钾', priority: 'urgent', reason: '利尿后监测', timing: 'today', instructions: '' },
        rationale: '防止低钾', citations: [], session_id: 'session-1', source_message_id: 'message-1',
        created_by: 'doctor-1', created_at: '2026-07-20T08:00:00Z', updated_at: '2026-07-20T08:00:00Z',
      }],
    });
    service.decideAssistantActionDraft.mockResolvedValue({ patient_id: 'patient-1', state_version: 12, drafts: [] });
    renderPanel();
    fireEvent.click(screen.getByLabelText('展开查房助手'));
    fireEvent.click(await screen.findByRole('button', { name: '批准并执行' }));

    const dialog = screen.getByRole('dialog');
    expect((screen.getByRole('button', { name: '确认批准并执行' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByRole('textbox', { name: /审核意见/ }), { target: { value: '已核对当前用药和肾功能' } });
    fireEvent.click(screen.getByRole('button', { name: '确认批准并执行' }));

    await waitFor(() => expect(service.decideAssistantActionDraft).toHaveBeenCalledWith(
      'patient-1',
      'draft-investigation',
      'approve',
      { comment: '已核对当前用药和肾功能', expected_version: 11 },
    ));
  });

  it('opens the formal clinical record for an approved assistant draft', async () => {
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    service.fetchAssistantActionDrafts.mockResolvedValue({
      patient_id: 'patient-1',
      state_version: 12,
      drafts: [{
        id: 'draft-complete', draft_type: 'follow_up_task', status: 'approved',
        payload: { title: '出院后一周电话随访', due_at: '2026-08-01T09:00:00+08:00', assignee: '随访护士' },
        rationale: '评估出院后症状和依从性', citations: [], session_id: 'session-1', source_message_id: 'message-1',
        created_by: 'doctor-1', created_at: '2026-07-21T08:00:00Z', updated_at: '2026-07-21T08:00:00Z',
        execution: { record_type: 'follow_up_task', record_id: 'follow-up-1', status: 'pending' },
      }],
    });
    const onOpenClinicalRecord = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><PatientAssistantPanel patientId="patient-1" onOpenClinicalRecord={onOpenClinicalRecord} /></QueryClientProvider>);
    fireEvent.click(screen.getByLabelText('展开查房助手'));

    fireEvent.click(await screen.findByRole('button', { name: '查看正式记录' }));

    expect(onOpenClinicalRecord).toHaveBeenCalledWith(expect.objectContaining({ id: 'draft-complete', execution: { record_type: 'follow_up_task', record_id: 'follow-up-1', status: 'pending' } }));
  });
});
