import { describe, expect, it } from 'vitest';

import { displayValue, readinessPercent, scoreTone } from './dashboard-utils';

describe('dashboard utils', () => {
  it('derives a bounded discharge readiness percentage from backend criteria', () => {
    expect(readinessPercent({ met_count: 3, total_count: 4 })).toBe(75);
    expect(readinessPercent({ score: 140 })).toBe(100);
    expect(readinessPercent()).toBeNull();
  });

  it('maps NEWS2 score bands to restrained clinical tones', () => {
    expect(scoreTone(7)).toBe('error');
    expect(scoreTone(5)).toBe('warning');
    expect(scoreTone(2)).toBe('success');
  });

  it('renders nested clinical values without leaking object stringification', () => {
    expect(displayValue({ objective: { spo2: 96, trend: 'stable' }, findings: ['edema', 'dyspnea'] })).toBe('objective: spo2: 96；trend: stable；findings: edema；dyspnea');
  });
});
