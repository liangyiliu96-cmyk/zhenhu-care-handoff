import { describe, expect, it } from 'vitest';

import { commandNeedsTarget, commandRequiresReason } from './command-utils';

describe('clinical command requirements', () => {
  it('requires a target for transfer and consultation only', () => {
    expect(commandNeedsTarget('transfer')).toBe(true);
    expect(commandNeedsTarget('consult')).toBe(true);
    expect(commandNeedsTarget('hold')).toBe(false);
  });

  it('requires a clinical reason for state-changing commands except resume', () => {
    expect(commandRequiresReason('hold')).toBe(true);
    expect(commandRequiresReason('discharge')).toBe(true);
    expect(commandRequiresReason('resume')).toBe(false);
  });
});
