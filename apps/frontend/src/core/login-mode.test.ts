import { describe, expect, it } from 'vitest';

import { loginModeDescription, normalizeLoginMode, supportsCredentialLogin } from './login-mode';

describe('login mode helpers', () => {
  it('uses header mode as the safe fallback for an unknown frontend setting', () => {
    expect(normalizeLoginMode('unexpected')).toBe('header');
  });

  it('allows credential login only for supported local modes', () => {
    expect(supportsCredentialLogin('header')).toBe(true);
    expect(supportsCredentialLogin('jwt')).toBe(true);
    expect(supportsCredentialLogin('oidc')).toBe(false);
  });

  it('does not describe oidc as a password-based flow', () => {
    expect(loginModeDescription('oidc')).toContain('统一身份认证');
  });
});
