import { describe, expect, it } from 'vitest';

import { graphNeighbors, layoutEvidenceGraph, relationLabel } from './evidence-graph-layout';

const graph = {
  disease_id: 'heart_failure',
  root_id: 'disease:heart_failure',
  nodes: [
    { id: 'disease:heart_failure', kind: 'disease' as const, label: '心力衰竭' },
    { id: 'e-1', kind: 'evidence' as const, label: '容量管理', source: '指南 A', layer: 'L5' },
    { id: 'r-1', kind: 'rule' as const, label: '每日监测体重', relation: 'HAS_MONITORING_RULE' },
  ],
  edges: [
    { id: 'e-1|ABOUT_DISEASE|disease:heart_failure', source: 'e-1', target: 'disease:heart_failure', relation: 'ABOUT_DISEASE' },
    { id: 'disease:heart_failure|HAS_MONITORING_RULE|r-1', source: 'disease:heart_failure', target: 'r-1', relation: 'HAS_MONITORING_RULE' },
  ],
};

describe('evidence graph layout', () => {
  it('retains every safe graph item in an interactive flow layout', () => {
    const layout = layoutEvidenceGraph(graph);

    expect(layout.nodes).toHaveLength(3);
    expect(layout.edges).toHaveLength(2);
    expect(layout.edges[1]?.animated).toBe(true);
    expect(layout.nodes.every((node) => Number.isFinite(node.position.x) && Number.isFinite(node.position.y))).toBe(true);
  });

  it('keeps focus scoped to a node and its immediate graph relationships', () => {
    expect([...graphNeighbors('disease:heart_failure', graph.edges)]).toEqual(expect.arrayContaining(['disease:heart_failure', 'e-1', 'r-1']));
    expect(relationLabel('HAS_MONITORING_RULE')).toBe('监测重点');
  });
});
