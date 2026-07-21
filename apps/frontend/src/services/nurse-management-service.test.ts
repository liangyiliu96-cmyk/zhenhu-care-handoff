// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { completeNursingTask, fetchMonitoringOverdue, fetchNursingKpi } from './nurse-management-service';

afterEach(() => vi.unstubAllGlobals());

describe('nurse management service', () => {
  it('requests the monitoring overdue queue through the unified client', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { total: 0, critical_overdue: 0, patients: [] } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchMonitoringOverdue();

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/monitoring/overdue');
  });

  it('sends nursing task completion with optimistic locking and an idempotency key', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { completion: { id: 'done-1' }, state_version: 8 } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await completeNursingTask('patient/1', {
      task_type: 'vital_signs', task_key: 'vital_signs:abc', note: '已测量', expected_version: 7,
    }, 'task-key-1');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/nurse/tasks/patient%2F1/complete');
    const options = fetchMock.mock.calls[0]?.[1];
    expect(options?.method).toBe('POST');
    expect((options?.headers as Record<string, string>)['Idempotency-Key']).toBe('task-key-1');
    expect(JSON.parse(String(options?.body))).toEqual({
      task_type: 'vital_signs', task_key: 'vital_signs:abc', note: '已测量', expected_version: 7,
    });
  });

  it('requests the department-scoped nursing KPI snapshot', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify({ data: { open_tasks: 0 } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchNursingKpi();

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/nurse/kpi');
  });
});
