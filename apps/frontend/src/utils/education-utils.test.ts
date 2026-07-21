import { describe, expect, it } from 'vitest';

import { educationQuery } from './education-utils';

describe('educationQuery', () => {
  it('keeps patient education and emergency discovery queries separate', () => {
    expect(educationQuery('心力衰竭', 'guidance')).toContain('患者教育');
    expect(educationQuery('心力衰竭', 'emergency')).toContain('急诊识别');
  });

  it('uses a neutral fallback when the disease label is unavailable', () => {
    expect(educationQuery('', 'guidance')).toContain('出院患者');
  });
});
