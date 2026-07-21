// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchWardLabSummary, fetchWardPriority, fetchWardTrends, fetchWardVisitOrder, fetchWardVitals, normalizeWorkspaceAlert } from './ward-service';

afterEach(() => vi.unstubAllGlobals());

describe('normalizeWorkspaceAlert', () => {
  it('flattens the ward alert envelope and uses semantic severity', () => {
    expect(normalizeWorkspaceAlert({
      patient_id: 'patient-1',
      name: '王某',
      severity: '🔴',
      alert: { alert_id: 'alert-1', message: '血钾危急值', status: 'open', severity: 'critical' },
    })).toMatchObject({
      patient_id: 'patient-1',
      alert_id: 'alert-1',
      message: '血钾危急值',
      severity: 'critical',
    });
  });

  it('falls back to the workspace severity when the alert body has no severity', () => {
    expect(normalizeWorkspaceAlert({
      patient_id: 'patient-2',
      name: '李某',
      severity: '🟡',
      alert: { message: '需要持续监测' },
    }).severity).toBe('warning');
  });

  it('uses the registered ward clinical board endpoints', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: {} }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await Promise.all([
      fetchWardVitals('spo2'),
      fetchWardTrends(),
      fetchWardVisitOrder(),
      fetchWardPriority(),
      fetchWardLabSummary(),
    ]);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      '/ward/vitals?vital=spo2',
      '/ward/trends',
      '/ward/visit-order',
      '/ward/priority',
      '/ward/lab-summary',
    ]);
  });
});
