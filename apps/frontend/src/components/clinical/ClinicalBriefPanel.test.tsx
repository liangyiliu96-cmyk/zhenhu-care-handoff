import { describe, expect, it } from 'vitest';

import { formatBriefValue } from '@/utils/clinical-brief-utils';

describe('formatBriefValue', () => {
  it('renders structured clinical assessment values without returning an object', () => {
    expect(formatBriefValue({
      stability: 'stable',
      response_to_treatment: 'improving',
      key_findings: ['SpO2 stable', 'no edema'],
    })).toBe('stability: stable；response_to_treatment: improving；key_findings: SpO2 stable；no edema');
  });

  it('handles arrays and empty values deterministically', () => {
    expect(formatBriefValue(['A', { next_labs: 'BMP' }, null])).toBe('A；next_labs: BMP');
  });
});
