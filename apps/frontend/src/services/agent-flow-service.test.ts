// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAgentFlow } from './agent-flow-service';

afterEach(() => vi.unstubAllGlobals());

describe('agent flow service', () => {
  it('loads the workflow projection through the patient-scoped route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({
      data: {
        patient_id: 'patient-1', flow_status: 'ready', state_version: 3,
        pending_review: null, stages: [], generated_artifacts: [], citations: [],
        turn_journal: [], safety_boundary: 'human review required',
      },
    }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchAgentFlow('patient/1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/inpatient/patient%2F1/agent-flow',
      expect.objectContaining({ method: 'GET' }),
    );
  });
});
