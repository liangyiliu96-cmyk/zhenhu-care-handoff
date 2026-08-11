// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/config/api', () => ({
  AUTH_MODE: 'oidc',
  OIDC_LOGIN_URL: '',
  OIDC_AUTHORITY: 'http://idp.test/realms/zhenhu',
  OIDC_CLIENT_ID: 'zhenhu-web',
  OIDC_REDIRECT_URI: 'http://localhost/callback',
  DEV_SHORTCUT_LOGIN_ENABLED: false,
}));

vi.mock('@/core/oidc', () => ({
  isOidcMode: vi.fn(() => true),
  loginWithOidc: vi.fn(),
  processOidcCallback: vi.fn(),
  logoutOidc: vi.fn(),
  getOidcAccessToken: vi.fn(),
}));

vi.mock('@/services/auth-service', () => ({
  fetchWhoami: vi.fn(),
  loginWithCredentials: vi.fn(),
  loginWithDevShortcut: vi.fn(),
}));

import { fetchWhoami } from '@/services/auth-service';
import {
  getOidcAccessToken,
  isOidcMode,
  loginWithOidc,
  logoutOidc,
  processOidcCallback,
} from '@/core/oidc';
import { useAuthStore } from './auth-store';
import type { UserIdentity } from '@/types/auth';

const oidcIdentity: UserIdentity = {
  name: '张医生',
  role: 'doctor',
  title: '主治医师',
  department: '心内科',
  actor_id: 'sub-123',
  job_number: 'sub-123',
};

function resetStore() {
  useAuthStore.setState({
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
  });
}

beforeEach(() => {
  sessionStorage.clear();
  resetStore();
  vi.clearAllMocks();
});

describe('auth-store OIDC mode', () => {
  it('establishes a session from the authorization callback and mirrors the identity', async () => {
    vi.mocked(processOidcCallback).mockResolvedValue({ identity: oidcIdentity, token: 'access-token-1' });

    const route = await useAuthStore.getState().completeOidcLogin();

    expect(route).toContain('/department/');
    expect(route).toContain('/doctor');
    expect(useAuthStore.getState().user).toMatchObject({ name: '张医生', role: 'doctor', department: '心内科' });
    expect(useAuthStore.getState().token).toBe('access-token-1');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(sessionStorage.getItem('zhenhu_role')).toBe('doctor');
    expect(sessionStorage.getItem('zhenhu_token')).toBe('access-token-1');
  });

  it('surfaces an error when the authorization callback fails', async () => {
    vi.mocked(processOidcCallback).mockRejectedValue(new Error('invalid state'));

    await expect(useAuthStore.getState().completeOidcLogin()).rejects.toThrow('invalid state');
    expect(useAuthStore.getState().error).toContain('invalid state');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('starts the SSO redirect through the OIDC client', async () => {
    vi.mocked(loginWithOidc).mockResolvedValue(undefined);
    await useAuthStore.getState().loginWithOidc();
    expect(loginWithOidc).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('clears the local session and signs out of the IdP', async () => {
    sessionStorage.setItem('zhenhu_role', 'doctor');
    sessionStorage.setItem('zhenhu_token', 't');
    resetStore();
    useAuthStore.setState({ user: oidcIdentity, token: 't', isAuthenticated: true });
    vi.mocked(logoutOidc).mockResolvedValue(undefined);

    useAuthStore.getState().logout();

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(sessionStorage.getItem('zhenhu_role')).toBeNull();
    expect(logoutOidc).toHaveBeenCalledTimes(1);
    expect(isOidcMode).toHaveBeenCalled();
  });

  it('verifies an existing OIDC session against the backend whoami endpoint', async () => {
    vi.mocked(getOidcAccessToken).mockResolvedValue('access-token-1');
    vi.mocked(fetchWhoami).mockResolvedValue(oidcIdentity);

    await useAuthStore.getState().verifySession();

    expect(getOidcAccessToken).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().user).toMatchObject({ name: '张医生' });
    expect(useAuthStore.getState().token).toBe('access-token-1');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it('marks the session unauthenticated when no OIDC token exists', async () => {
    vi.mocked(getOidcAccessToken).mockResolvedValue(null);

    await useAuthStore.getState().verifySession();

    expect(fetchWhoami).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
