import { describe, expect, it } from 'vitest';

import { adminTabsFor } from './admin-tabs';

describe('adminTabsFor', () => {
  it('keeps doctor management in the shared administrative views', () => {
    expect(adminTabsFor({ role: 'doctor', title: '科主任' }).map((item) => item.id)).toEqual([
      'overview', 'evidence_graph', 'knowledge', 'templates', 'organization', 'ward', 'integrations', 'operations',
    ]);
  });

  it('gives head nurses the same governed knowledge base alongside nursing oversight', () => {
    expect(adminTabsFor({ role: 'nurse', title: '护士长' }).map((item) => item.id)).toEqual([
      'overview', 'evidence_graph', 'nursing', 'handoff', 'checklist', 'knowledge', 'templates', 'organization', 'integrations', 'operations',
    ]);
  });

  it('keeps knowledge governance distinct from the default evidence graph for a department manager', () => {
    const tabs = adminTabsFor({ role: 'nurse', title: '护士长', department: '心内科' });
    expect(tabs.find((item) => item.id === 'knowledge')?.path).toBe('/department/%E5%BF%83%E5%86%85%E7%A7%91/management?tab=knowledge');
    expect(tabs.find((item) => item.id === 'evidence_graph')?.path).toBe('/department/%E5%BF%83%E5%86%85%E7%A7%91/management?tab=evidence_graph');
  });

  it('routes a doctor manager to the explicit knowledge governance tab', () => {
    const tabs = adminTabsFor({ role: 'doctor', title: '科主任', department: '心内科' });
    expect(tabs.find((item) => item.id === 'knowledge')?.path).toBe('/department/%E5%BF%83%E5%86%85%E7%A7%91/management?tab=knowledge');
  });
});
