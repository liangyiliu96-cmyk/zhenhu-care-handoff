// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import WardClinicalBoard from './WardClinicalBoard';

const hooks = vi.hoisted(() => ({
  useWardLabSummary: vi.fn(),
  useWardPriority: vi.fn(),
  useWardTrends: vi.fn(),
  useWardVisitOrder: vi.fn(),
  useWardVitals: vi.fn(),
}));

const service = vi.hoisted(() => ({
  fetchWardPriority: vi.fn(),
  fetchWardVisitOrder: vi.fn(),
}));

vi.mock('@/hooks/use-ward', () => hooks);
vi.mock('@/services/ward-service', () => service);

const query = <T,>(data: T) => ({ data, error: null, isLoading: false, refetch: vi.fn() });

const visitOrder = {
  reason: '共2名患者，按临床紧急度排序。',
  total: 3,
  urgent: 1,
  stable: 2,
  visit_order: [
    {
      patient_id: 'patient-urgent', name: '李静安', risk: 'high', news2: 7, alerts: 2,
      has_pending: true, deteriorating: true, spo2: 90, hr: 112, round_count: 0, department: '心内科',
    },
    {
      patient_id: 'patient-stable', name: '周明', risk: 'low', news2: 1, alerts: 0,
      has_pending: false, deteriorating: false, spo2: 97, hr: 76, round_count: 1, department: '心内科',
    },
    {
      patient_id: 'patient-new', name: '陈悦', risk: 'medium', news2: null, alerts: 0,
      has_pending: false, deteriorating: false, spo2: null, hr: null, round_count: 0, department: '心内科',
    },
  ],
};

beforeEach(() => {
  hooks.useWardVisitOrder.mockReturnValue(query(visitOrder));
  hooks.useWardVitals.mockReturnValue(query({ total: 0, vital: 'spo2', summary: { improving: 0, stable: 0, declining: 0 }, patients: [] }));
  hooks.useWardTrends.mockReturnValue(query({ total: 0, deteriorating: 0, patients: [] }));
  hooks.useWardPriority.mockReturnValue(query({ total: 0, top_patients: [], reasoning: '' }));
  hooks.useWardLabSummary.mockReturnValue(query({ total: 0, patients_affected: 0, abnormal_labs: [] }));
  service.fetchWardVisitOrder.mockResolvedValue(visitOrder);
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function renderBoard(onOpenPatient = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { onOpenPatient, ...render(<QueryClientProvider client={client}><WardClinicalBoard onOpenPatient={onOpenPatient} /></QueryClientProvider>) };
}

describe('WardClinicalBoard round priority queue', () => {
  it('shows the read-only round priority queue with reasons and patient status', () => {
    renderBoard();

    expect(screen.getByText('查房优先顺序')).toBeTruthy();
    expect(screen.getByText('共2名患者，按临床紧急度排序。')).toBeTruthy();
    expect(screen.getByText('李静安')).toBeTruthy();
    expect(screen.getByText('恶化')).toBeTruthy();
    expect(screen.getByText('待审')).toBeTruthy();
    expect(screen.getByText('周明')).toBeTruthy();
  });

  it('opens only the selected patient when a priority row is clicked', () => {
    const onOpenPatient = vi.fn();
    renderBoard(onOpenPatient);

    fireEvent.click(screen.getByRole('button', { name: /李静安/ }));

    expect(onOpenPatient).toHaveBeenCalledTimes(1);
    expect(onOpenPatient).toHaveBeenCalledWith('patient-urgent');
    expect(service.fetchWardVisitOrder).not.toHaveBeenCalled();
  });
});
