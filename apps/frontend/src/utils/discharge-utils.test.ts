import { describe, expect, it } from 'vitest';

import { canSignDischarge, dischargeBlockers } from './discharge-utils';

describe('discharge-utils', () => {
  it('allows signature only when the backend marks every criterion as met', () => {
    expect(canSignDischarge({ all_met: true })).toBe(true);
    expect(canSignDischarge({ all_met: false })).toBe(false);
    expect(canSignDischarge(null)).toBe(false);
  });

  it('normalizes the backend-provided unmet criterion list', () => {
    expect(dischargeBlockers({ unmet: ['血压待稳定', 3] })).toEqual(['血压待稳定', '3']);
    expect(dischargeBlockers({ unmet: 'not-an-array' })).toEqual([]);
  });
});
