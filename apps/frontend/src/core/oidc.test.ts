// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = vi.hoisted(() => ({
  signinRedirect: vi.fn(),
  signinRedirectCallback: vi.fn(),
  signoutRedirect: vi.fn(),
  removeUser: vi.fn(),
  getUser: vi.fn(),
}));

vi.mock('oidc-client-ts', () => ({
  UserManager: class MockUserManager {
    signinRedirect = manager.signinRedirect;
    signinRedirectCallback = manager.signinRedirectCallback;
    signoutRedirect = manager.signoutRedirect;
    removeUser = manager.removeUser;
    getUser = manager.getUser;
  },
}));

vi.mock('@/config/api', () => ({
  AUTH_MODE: 'oidc',
  OIDC_LOGIN_URL: '',
  OIDC_AUTHORITY: 'http://idp.test/realms/zhenhu',
  OIDC_CLIENT_ID: 'zhenhu-web',
  OIDC_REDIRECT_URI: 'http://localhost/callback',
  DEV_SHORTCUT_LOGIN_ENABLED: false,
}));

import {
  buildOidcSettings,
  extractRoles,
  getOidcAccessToken,
  getUserManager,
  isOidcMode,
  loginWithOidc,
  logoutOidc,
  mapOidcUserToIdentity,
  mapProfileToIdentity,
  markOidcRedirectStarted,
  processOidcCallback,
  resetOidcRedirectGuardForTest,
  resetUserManagerForTest,
  resolveRole,
  syncTokenMirror,
} from './oidc';

const fakeUser = (overrides: Record<string, unknown> = {}) => ({
  access_token: 'access-token-1',
  profile: {
    sub: 'sub-123',
    preferred_username: 'zhang.doctor',
    name: '张医生',
    roles: ['doctor'],
    title: '主治医师',
    department: '心内科',
    ...overrides,
  },
});

beforeEach(() => {
  sessionStorage.clear();
  resetUserManagerForTest();
  vi.clearAllMocks();
  manager.signinRedirect.mockResolvedValue(undefined);
  manager.signoutRedirect.mockResolvedValue(undefined);
  manager.removeUser.mockResolvedValue(undefined);
});

afterEach(() => {
  resetUserManagerForTest();
});

describe('oidc mode helpers', () => {
  it('reports oidc mode from the mocked AUTH_MODE', () => {
    expect(isOidcMode()).toBe(true);
  });

  it('builds Authorization Code + PKCE settings from environment', () => {
    const settings = buildOidcSettings();
    expect(settings.authority).toBe('http://idp.test/realms/zhenhu');
    expect(settings.client_id).toBe('zhenhu-web');
    expect(settings.redirect_uri).toBe('http://localhost/callback');
    expect(settings.response_type).toBe('code');
    expect(settings.scope).toBe('openid profile roles');
    expect(settings.automaticSilentRenew).toBe(false);
  });

  it('lazily creates and reuses the UserManager singleton', () => {
    const first = getUserManager();
    const second = getUserManager();
    expect(second).toBe(first);
  });

  it('deduplicates OIDC redirect starts until the guard is reset', () => {
    resetOidcRedirectGuardForTest();
    expect(markOidcRedirectStarted()).toBe(true);
    expect(markOidcRedirectStarted()).toBe(false);
    resetOidcRedirectGuardForTest();
    expect(markOidcRedirectStarted()).toBe(true);
  });
});

describe('claim mapping', () => {
  it('maps standard claims to a doctor identity', () => {
    const identity = mapProfileToIdentity({
      sub: 'sub-1',
      preferred_username: 'doctor.a',
      name: '张医生',
      roles: ['doctor'],
      title: '主治医师',
      department: '心内科',
    });
    expect(identity).toMatchObject({
      name: '张医生',
      role: 'doctor',
      title: '主治医师',
      department: '心内科',
      actor_id: 'sub-1',
      job_number: 'sub-1',
    });
  });

  it('falls back to preferred_username and then sub for the display name', () => {
    expect(mapProfileToIdentity({ sub: 's1', preferred_username: 'nurse.b' }).name).toBe('nurse.b');
    expect(mapProfileToIdentity({ sub: 's2' }).name).toBe('s2');
  });

  it('extracts nurse role from realm_access and resource_access', () => {
    const roles = extractRoles({
      realm_access: { roles: ['offline_access', 'nurse'] },
      resource_access: { 'zhenhu-web': { roles: ['nurse'] } },
    });
    expect(resolveRole(roles)).toBe('nurse');
  });

  it('uses the first non-empty department from claims', () => {
    const identity = mapProfileToIdentity({ sub: 's', roles: ['doctor'], department: '', departments: ['呼吸科', '心内科'] });
    expect(identity.department).toBe('呼吸科');
  });

  it('maps a User object through the same identity builder', () => {
    const identity = mapOidcUserToIdentity(fakeUser() as never);
    expect(identity.role).toBe('doctor');
    expect(identity.name).toBe('张医生');
  });
});

describe('oidc flow', () => {
  it('redirects to the IdP via signinRedirect', async () => {
    await loginWithOidc();
    expect(manager.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it('handles the authorization callback and mirrors the access token', async () => {
    manager.signinRedirectCallback.mockResolvedValue(fakeUser());
    const { identity, token } = await processOidcCallback();
    expect(manager.signinRedirectCallback).toHaveBeenCalledTimes(1);
    expect(token).toBe('access-token-1');
    expect(identity.actor_id).toBe('sub-123');
    expect(sessionStorage.getItem('zhenhu_token')).toBe('access-token-1');
  });

  it('rejects the callback when no access token is returned', async () => {
    manager.signinRedirectCallback.mockResolvedValue({ profile: { sub: 's' } });
    await expect(processOidcCallback()).rejects.toThrow(/未返回访问令牌/);
  });

  it('reads the latest access token from the UserManager and syncs the mirror', async () => {
    manager.getUser.mockResolvedValue({ access_token: 'fresh-token', profile: {} });
    expect(await getOidcAccessToken()).toBe('fresh-token');
    expect(sessionStorage.getItem('zhenhu_token')).toBe('fresh-token');
  });

  it('returns null when no OIDC session exists', async () => {
    manager.getUser.mockResolvedValue(null);
    expect(await getOidcAccessToken()).toBeNull();
  });

  it('clears the local user and redirects to the IdP end-session endpoint on logout', async () => {
    await logoutOidc();
    expect(manager.removeUser).toHaveBeenCalledTimes(1);
    expect(manager.signoutRedirect).toHaveBeenCalledTimes(1);
  });

  it('writes and removes the token mirror explicitly', () => {
    syncTokenMirror('abc');
    expect(sessionStorage.getItem('zhenhu_token')).toBe('abc');
    syncTokenMirror(null);
    expect(sessionStorage.getItem('zhenhu_token')).toBeNull();
  });
});
