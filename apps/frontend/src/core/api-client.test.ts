import { describe, expect, it } from 'vitest';

import { describeApiError, resolveApiUrl } from './api-client';
import { ApiClientError } from './api-client';

describe('resolveApiUrl', () => {
  it('uses the configured API base for deployment builds', () => {
    expect(resolveApiUrl('/inpatient/whoami', 'https://api.example.test/')).toBe(
      'https://api.example.test/inpatient/whoami'
    );
  });

  it('keeps relative paths when a same-origin reverse proxy is used', () => {
    expect(resolveApiUrl('/inpatient/whoami', '')).toBe('/inpatient/whoami');
  });
});

describe('describeApiError', () => {
  it('gives actionable clinical messages for access and conflict errors', () => {
    expect(describeApiError(new ApiClientError(403, 'FORBIDDEN', 'forbidden'))).toContain('无权访问');
    expect(describeApiError(new ApiClientError(409, 'STATE_VERSION_CONFLICT', 'conflict'))).toContain('刷新');
  });
});
