import { describe, expect, it } from 'vitest';

import { formatBriefValue, localizeClinicalText } from './clinical-brief-utils';

describe('clinical brief localization', () => {
  it('translates internal clinical keys and review states', () => {
    expect(localizeClinicalText('复核：creatinine变化')).toBe('复核：肌酐变化');
    expect(localizeClinicalText('等待医生审核：med_confirm')).toBe('等待医生审核：用药调整审核');
    expect(formatBriefValue({ potassium: '上升' })).toBe('血钾: 上升');
  });
});
