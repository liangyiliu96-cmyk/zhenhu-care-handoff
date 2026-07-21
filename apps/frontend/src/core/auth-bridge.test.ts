// @vitest-environment jsdom

import { describe, expect, it } from 'vitest';

import { encodeAuthHeaderValue, getAuthHeaders, setDevIdentity } from './auth-bridge';

describe('encodeAuthHeaderValue', () => {
  it('converts Chinese development identity fields into valid HTTP header values', () => {
    const encoded = encodeAuthHeaderValue('心内科');

    expect(encoded).toMatch(/^[\x00-\x7F]+$/);
    expect(decodeURIComponent(encoded)).toBe('心内科');
  });

  it('includes the stable development actor ID when an identity is selected', () => {
    sessionStorage.clear();
    setDevIdentity({ role: 'doctor', title: '主治医师', department: '心内科', actorId: 'dev-doc-lu' });

    expect(getAuthHeaders()['x-user-id']).toBe('dev-doc-lu');
  });
});
