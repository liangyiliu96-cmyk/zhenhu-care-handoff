import { describe, expect, it } from 'vitest';

import { nurseBoardTab } from './nurse-workspace';

describe('nurseBoardTab', () => {
  it.each([
    [null, 'overview'],
    ['', 'overview'],
    ['tasks', 'tasks'],
    ['overview', 'overview'],
    ['patients', 'patients'],
    ['overdue', 'overdue'],
    ['shift', 'shift'],
    ['checklist', 'checklist'],
    ['unknown', 'overview'],
  ] as const)('resolves %s to %s', (value, expected) => {
    expect(nurseBoardTab(value)).toBe(expected);
  });
});
