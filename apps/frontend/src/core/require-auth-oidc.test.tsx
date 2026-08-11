// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const oidc = vi.hoisted(() => ({
  isOidcMode: vi.fn(() => true),
  loginWithOidc: vi.fn(),
  markOidcRedirectStarted: vi.fn(() => true),
  resetOidcRedirectGuardForTest: vi.fn(),
}));

vi.mock('@/core/oidc', () => ({
  isOidcMode: oidc.isOidcMode,
  loginWithOidc: oidc.loginWithOidc,
  markOidcRedirectStarted: oidc.markOidcRedirectStarted,
  resetOidcRedirectGuardForTest: oidc.resetOidcRedirectGuardForTest,
}));

const storeState = vi.hoisted(() => ({
  user: null as { name: string; role: 'doctor' | 'nurse'; title: string; department: string } | null,
  isAuthenticated: false,
}));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

import RequireAuth from './require-auth';
import { loginWithOidc, resetOidcRedirectGuardForTest } from '@/core/oidc';

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/workbench']}>
      <Routes>
        <Route path="/workbench" element={<RequireAuth><div>受保护内容</div></RequireAuth>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  resetOidcRedirectGuardForTest();
  storeState.user = null;
  storeState.isAuthenticated = false;
  sessionStorage.clear();
  vi.mocked(loginWithOidc).mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('RequireAuth OIDC redirect', () => {
  it('starts an SSO redirect when the visitor is unauthenticated', () => {
    renderProtected();
    expect(oidc.loginWithOidc).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('受保护内容')).toBeNull();
  });

  it('does not redirect when a stored session exists', () => {
    storeState.user = { name: '张医生', role: 'doctor', title: '主治医师', department: '心内科' };
    storeState.isAuthenticated = true;
    renderProtected();
    expect(oidc.loginWithOidc).not.toHaveBeenCalled();
    expect(screen.getByText('受保护内容')).toBeTruthy();
  });
});
