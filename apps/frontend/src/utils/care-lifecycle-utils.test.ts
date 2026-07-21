import { describe, expect, it } from 'vitest';

import { lifecycleStatusLabel, medicationTransitions } from './care-lifecycle-utils';

describe('care lifecycle adapters', () => {
  it('only exposes backend-allowed medication transitions', () => {
    expect(medicationTransitions('draft')).toEqual([{ status: 'active', label: '激活医嘱' }, { status: 'cancelled', label: '取消医嘱' }]);
    expect(medicationTransitions('active')).toEqual([{ status: 'held', label: '暂停医嘱' }, { status: 'discontinued', label: '停用医嘱' }]);
    expect(medicationTransitions('discontinued')).toEqual([]);
  });

  it('uses readable labels without guessing unknown lifecycle states', () => {
    expect(lifecycleStatusLabel('requested')).toBe('待处理');
    expect(lifecycleStatusLabel('external-state')).toBe('external-state');
  });
});
