// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchFollowUpOverview } from './follow-up-service';

afterEach(() => vi.unstubAllGlobals());

describe('follow-up service', () => {
  it('requests the scoped post-discharge overview with its selected filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { summary: {}, patients: [], pagination: {} } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchFollowUpOverview({ status: 'overdue', limit: 20, offset: 40 });

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/follow-up-overview?status=overdue&limit=20&offset=40');
  });
});
