import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('@/core/api-client', () => api);

import { fetchPatientDirectory } from './patient-directory-service';

describe('fetchPatientDirectory', () => {
  beforeEach(() => api.apiGet.mockReset());

  it('passes server-side filters and pagination to the patient directory endpoint', async () => {
    api.apiGet.mockResolvedValue({});
    await fetchPatientDirectory({ search: '张', phase: 'monitoring', risk_level: 'high', sort: 'name', limit: 20, offset: 40 });
    expect(String(api.apiGet.mock.calls[0]?.[0])).toBe('/patients?phase=monitoring&risk_level=high&search=%E5%BC%A0&sort=name&limit=20&offset=40');
  });
});
