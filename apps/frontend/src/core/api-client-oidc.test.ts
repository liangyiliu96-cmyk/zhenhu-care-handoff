// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/config/api', () => ({
  API_BASE: '',
  API_TIMEOUT_READ: 1000,
  API_TIMEOUT_WRITE: 1000,
  API_TIMEOUT_CLINICAL: 1000,
  API_TIMEOUT_AGENT: 1000,
  AUTH_MODE: 'oidc',
  OIDC_LOGIN_URL: '',
  OIDC_AUTHORITY: 'http://idp.test/realms/zhenhu',
  OIDC_CLIENT_ID: 'zhenhu-web',
  OIDC_REDIRECT_URI: 'http://localhost/callback',
  DEV_SHORTCUT_LOGIN_ENABLED: false,
}));

vi.mock('./oidc', () => ({
  getOidcAccessToken: vi.fn(),
}));

import { getOidcAccessToken } from './oidc';
import { apiGet } from './api-client';

const fetchMock = vi.fn();

beforeEach(() => {
  vi.mocked(getOidcAccessToken).mockResolvedValue('oidc-access-token-123');
  fetchMock.mockReset();
  global.fetch = fetchMock;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('api-client OIDC bearer attachment', () => {
  it('attaches Authorization: Bearer from the OIDC UserManager', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: { name: '张医生' }, error: null }),
    } as Response);

    const data = await apiGet<{ name: string }>('/inpatient/whoami');
    expect(data.name).toBe('张医生');

    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).headers).toMatchObject({ Authorization: 'Bearer oidc-access-token-123' });
  });

  it('does not attach a Bearer header when no OIDC session exists', async () => {
    vi.mocked(getOidcAccessToken).mockResolvedValue(null);
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: { ok: true }, error: null }),
    } as Response);

    await apiGet('/inpatient/whoami');
    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).headers).not.toHaveProperty('Authorization');
  });

  it('emits auth-expired and throws on a 401 response', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: { code: 'UNAUTHORIZED', message: 'expired' } }),
    } as Response);

    const listener = vi.fn();
    window.addEventListener('zhenhu:auth-expired', listener);

    await expect(apiGet('/inpatient/whoami')).rejects.toThrow('会话已过期');
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener('zhenhu:auth-expired', listener);
  });
});
