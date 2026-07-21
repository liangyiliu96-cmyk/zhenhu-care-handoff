import { describe, expect, it } from 'vitest';

import { canSubmitCareAction } from './care-utils';

describe('care action validation', () => {
  it('requires a complete medication order', () => {
    expect(canSubmitCareAction('medication', { medication: '阿司匹林', dose: '100mg', frequency: 'qd' })).toBe(true);
    expect(canSubmitCareAction('medication', { medication: '阿司匹林', dose: '', frequency: 'qd' })).toBe(false);
  });

  it('requires the backend fields for an investigation order', () => {
    expect(canSubmitCareAction('investigation', { testName: '心脏超声', reason: '评估心功能变化' })).toBe(true);
    expect(canSubmitCareAction('investigation', { testName: '心脏超声', reason: '' })).toBe(false);
  });

  it('requires the backend-required fields for MDT, education, and follow-up', () => {
    expect(canSubmitCareAction('mdt', { reason: '复杂心衰评估', specialties: '心内科,肾内科' })).toBe(true);
    expect(canSubmitCareAction('education', { topic: '抗凝用药', recipient: 'patient' })).toBe(true);
    expect(canSubmitCareAction('followup', { title: '一周复诊', dueAt: '2026-07-26' })).toBe(true);
    expect(canSubmitCareAction('followup', { title: '一周复诊', dueAt: '' })).toBe(false);
  });
});
