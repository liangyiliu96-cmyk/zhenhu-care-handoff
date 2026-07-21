// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { auditDischargePdfExport, createInvestigationOrder, editPatientRound, fetchNursingRecords, fetchPatientEvidenceGraph, fetchPatientRounds, generatePatientRound, generateWorkflowBrief, initiateDischarge, queryPatient, reviewPatientRound } from './patient-service';

afterEach(() => vi.unstubAllGlobals());

describe('patient service', () => {
  it('requests nursing records from the patient-scoped route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', total: 0, records: [] } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchNursingRecords('patient/1');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/nursing');
  });

  it('submits a scoped clinical question without using the assistant session route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', question: '风险？', answer: '需复评', citations: [] } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await queryPatient('patient-1', '风险？');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient-1/query');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ question: '风险？' });
  });

  it('audits a draft or final discharge PDF export before browser generation', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { audit_id: 'audit-1', state_version: 9 } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await auditDischargePdfExport('patient/1', 'draft');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/discharge-summary/export-audit');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ export_kind: 'draft' });
  });

  it('loads the complete patient rounds list', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', total: 0, rounds: [] } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchPatientRounds('patient/1');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/rounds');
  });

  it('generates a new round through the patient-scoped Agent route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', state_version: 10, round: {} } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await generatePatientRound('patient/1', 9);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/rounds/generate');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ expected_version: 9 });
  });

  it('records a doctor review for the selected round', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', state_version: 10, round: {} } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await reviewPatientRound('patient/1', 3, { expected_version: 9, comment: '已结合原始数据核对' });

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/rounds/3/review');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ expected_version: 9, comment: '已结合原始数据核对' });
  });

  it('stores a doctor revision separately from the Agent round draft', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', state_version: 10, round: {} } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await editPatientRound('patient/1', 3, { subjective: '气促好转', objective: '血压稳定', assessment: '继续观察容量状态', plan: '明晨复查电解质', attention: '关注低钾', expected_version: 9 });

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/rounds/3/edit');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ subjective: '气促好转', objective: '血压稳定', assessment: '继续观察容量状态', plan: '明晨复查电解质', attention: '关注低钾', expected_version: 9 });
  });

  it('generates a patient-scoped MDT coordination brief', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', state_version: 10, brief: {} } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await generateWorkflowBrief('patient/1', 'mdt', 9);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/workflow-briefs/mdt');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ expected_version: 9 });
  });

  it('loads graph pathway evidence through the patient-scoped route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', available: true, evidence: [], rules: [] } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchPatientEvidenceGraph('patient/1');

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/evidence-graph');
  });

  it('starts discharge through the formal discharge endpoint', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', status: 'pending_review' } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await initiateDischarge('patient/1', { reason: '患者符合出院条件', expected_version: 9 });

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/discharge/patient%2F1');
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ reason: '患者符合出院条件', expected_version: 9 });
  });

  it('creates an investigation order on the patient-scoped care route', async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, __?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ data: { patient_id: 'patient-1', investigation_order: {} } }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);

    await createInvestigationOrder('patient/1', {
      test_name: '心脏超声', priority: 'routine', reason: '评估心功能变化', timing: '', instructions: '', expected_version: 9,
    });

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/inpatient/patient%2F1/care/investigation-orders');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST');
  });
});
