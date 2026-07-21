// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import GlobalAssistantLauncher from './GlobalAssistantLauncher';
import { emitOpenGlobalAssistant } from '@/core/runtime-events';

const service = vi.hoisted(() => ({ fetchAssistantQuickQuestions: vi.fn() }));
vi.mock('@/services/assistant-service', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/assistant-service')>()),
  fetchAssistantQuickQuestions: service.fetchAssistantQuickQuestions,
}));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.clearAllMocks();
});

describe('GlobalAssistantLauncher', () => {
  it('opens a general assistant from a contextual assistant event', () => {
    sessionStorage.setItem('zhenhu_role', 'doctor');
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'doctor', questions: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><GlobalAssistantLauncher /></QueryClientProvider>);

    act(() => emitOpenGlobalAssistant('doctor'));
    expect(screen.getAllByText('查房助手').length).toBeGreaterThan(0);
    expect(screen.getByRole('textbox', { name: '向查房助手提问' })).toBeTruthy();
    expect(service.fetchAssistantQuickQuestions).toHaveBeenCalledWith('doctor', 'general', false);
    fireEvent.click(screen.getByRole('button', { name: '关闭查房助手' }));
    expect(screen.queryByRole('textbox', { name: '向查房助手提问' })).toBeNull();
  });

  it('opens the medication assistant as a distinct mode', () => {
    sessionStorage.setItem('zhenhu_role', 'doctor');
    service.fetchAssistantQuickQuestions.mockResolvedValue({ role: 'pharmacist', questions: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><GlobalAssistantLauncher /></QueryClientProvider>);

    act(() => emitOpenGlobalAssistant('pharmacist'));

    expect(screen.getAllByText('用药助手').length).toBeGreaterThan(0);
    expect(screen.getByRole('textbox', { name: '向用药助手提问' })).toBeTruthy();
    expect(service.fetchAssistantQuickQuestions).toHaveBeenCalledWith('pharmacist', 'general', false);
  });

  it('does not render for an unauthenticated visitor', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><GlobalAssistantLauncher /></QueryClientProvider>);

    expect(screen.queryByRole('button', { name: '打开查房助手' })).toBeNull();
  });
});
