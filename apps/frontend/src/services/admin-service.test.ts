// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearExpiredState, fetchCdsIntegrationStatus, fetchDiseaseEvidenceGraph, fetchDiseaseEvidenceGraphVisualization, fetchDiseaseTemplates, fetchEvidenceGraphStatus, fetchRagEntries, rebuildEvidenceGraph, reindexKnowledge, resetDemoPatients } from './admin-service';

afterEach(() => vi.unstubAllGlobals());

describe('admin service', () => {
  it('encodes a knowledge search query through the unified API client', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { layers: {}, search: '心衰', page: 1 } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchRagEntries('心衰', 'L4');

    expect(String(fetchMock.mock.calls[0][0])).toContain('search=%E5%BF%83%E8%A1%B0');
    expect(String(fetchMock.mock.calls[0][0])).toContain('page_size=30');
    expect(String(fetchMock.mock.calls[0][0])).toContain('layer=L4');
  });

  it('uses only audited management write routes for operations', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { audit_id: 'audit-1' } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await reindexKnowledge();
    await clearExpiredState();
    await resetDemoPatients();

    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(['/admin/rag/reindex', '/inpatient/clear-expired', '/inpatient/fixtures/reset-demo']);
    expect(fetchMock.mock.calls.every((call) => call[1]?.method === 'POST')).toBe(true);
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({ confirmed: true, purge_runtime: true });
  });

  it('loads manager-visible CDS integration readiness', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { service_count: 4, services: [] } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchCdsIntegrationStatus();

    expect(String(fetchMock.mock.calls[0][0])).toBe('/cds-services/status');
  });

  it('loads the server-owned disease template inventory without a write route', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { count: 1, templates: [{ disease_id: 'heart_failure', name: '心力衰竭', department: '心内科' }] } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDiseaseTemplates();

    expect(String(fetchMock.mock.calls[0][0])).toBe('/inpatient/templates');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('GET');
    expect(result.templates[0]?.disease_id).toBe('heart_failure');
  });

  it('uses the managed evidence graph routes for status, disease browsing and rebuild', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, init?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: init?.method === 'POST' ? { audit_id: 'audit-graph' } : { reachable: true } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchEvidenceGraphStatus();
    await fetchDiseaseEvidenceGraph('heart_failure');
    await fetchDiseaseEvidenceGraphVisualization('heart_failure');
    await rebuildEvidenceGraph();

    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(['/admin/evidence-graph/status', '/admin/evidence-graph/diseases/heart_failure', '/admin/evidence-graph/diseases/heart_failure/visualization', '/admin/evidence-graph/rebuild']);
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe('POST');
  });
});
