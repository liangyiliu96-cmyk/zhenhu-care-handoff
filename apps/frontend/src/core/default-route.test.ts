import { describe, expect, it } from 'vitest';

import { defaultRouteFor } from './default-route';

describe('defaultRouteFor', () => {
  it('sends department directors and head nurses to the shared admin page', () => {
    expect(defaultRouteFor({ role: 'doctor', title: '科主任' })).toBe('/admin');
    expect(defaultRouteFor({ role: 'nurse', title: '护士长' })).toBe('/admin');
  });

  it('keeps clinicians on their operational workspaces', () => {
    expect(defaultRouteFor({ role: 'doctor', title: '主治医师' })).toBe('/workbench');
    expect(defaultRouteFor({ role: 'nurse', title: '主管护师' })).toBe('/nurse');
  });

  it('uses a department-scoped workspace when the authenticated identity has a department', () => {
    expect(defaultRouteFor({ role: 'doctor', title: '主治医师', department: '呼吸科' })).toBe('/department/%E5%91%BC%E5%90%B8%E7%A7%91/doctor');
    expect(defaultRouteFor({ role: 'nurse', title: '护士长', department: '肾内科' })).toBe('/department/%E8%82%BE%E5%86%85%E7%A7%91/management');
  });
});
