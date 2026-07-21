import dagre from '@dagrejs/dagre';
import { MarkerType, Position, type Edge, type Node } from '@xyflow/react';

import type { EvidenceGraphVisualizationEdge, EvidenceGraphVisualizationNode, EvidenceGraphVisualizationResponse } from '@/types/evidence-graph';

export type EvidenceFlowData = EvidenceGraphVisualizationNode & Record<string, unknown>;
export type EvidenceFlowNode = Node<EvidenceFlowData>;
export type EvidenceFlowEdge = Edge<{ relation: string }>;

const NODE_DIMENSIONS: Record<EvidenceGraphVisualizationNode['kind'], { width: number; height: number }> = {
  disease:     { width: 90, height: 90 },
  evidence:    { width: 74, height: 74 },
  rule:        { width: 74, height: 74 },
  source:      { width: 58, height: 58 },
  layer:       { width: 52, height: 52 },
  department:  { width: 66, height: 66 },
};

const RELATION_LABELS: Record<string, string> = {
  ABOUT_DISEASE: '适用病种',
  SOURCED_FROM: '来源于',
  IN_LAYER: '所属知识层',
  OWNED_BY_DEPARTMENT: '归属科室',
  HAS_DISCHARGE_CRITERION: '出院标准',
  HAS_MEDICATION_RULE: '用药规则',
  HAS_MONITORING_RULE: '监测重点',
  HAS_CARE_TASK: '护理与随访',
};

function nodeStyle(kind: EvidenceGraphVisualizationNode['kind']) {
  const palette = {
    disease:    { bg: '#0B6472', border: '#0A5562', color: '#FFFFFF' },
    evidence:   { bg: '#D9ECF2', border: '#79ADBA', color: '#123943' },
    rule:       { bg: '#D4EFE3', border: '#75AF92', color: '#174837' },
    source:     { bg: '#FCE8C8', border: '#D7A664', color: '#66420F' },
    layer:      { bg: '#E8EDEB', border: '#AABBB7', color: '#314744' },
    department: { bg: '#F8DCDC', border: '#D58B8B', color: '#6D2A2A' },
  }[kind];

  const d = NODE_DIMENSIONS[kind];
  return {
    width: d.width,
    height: d.height,
    borderRadius: '50%',
    border: `2px solid ${palette.border}`,
    background: palette.bg,
    color: palette.color,
    fontSize: 11,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center' as const,
    lineHeight: 1.25,
    boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
  };
}

export function relationLabel(relation: string) {
  return RELATION_LABELS[relation] ?? relation.replaceAll('_', ' ');
}

export function layoutEvidenceGraph(graphData: EvidenceGraphVisualizationResponse): { nodes: EvidenceFlowNode[]; edges: EvidenceFlowEdge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: 'LR', ranksep: 160, nodesep: 40, marginx: 36, marginy: 36 });

  for (const node of graphData.nodes) graph.setNode(node.id, NODE_DIMENSIONS[node.kind]);
  for (const edge of graphData.edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);

  const nodes = graphData.nodes.map((node) => {
    const d = NODE_DIMENSIONS[node.kind];
    const position = graph.node(node.id) as { x: number; y: number };
    return {
      id: node.id,
      type: 'default',
      data: node as EvidenceFlowData,
      position: { x: position.x - d.width / 2, y: position.y - d.height / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: nodeStyle(node.kind),
    };
  });

  const edges = graphData.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    animated: edge.relation.startsWith('HAS_'),
    label: relationLabel(edge.relation),
    labelStyle: { fill: '#5F7074', fontSize: 10, fontWeight: 600 },
    labelBgStyle: { fill: '#F3F6F5', fillOpacity: 0.92 },
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
    style: { stroke: '#8AAAAD', strokeWidth: 1.4 },
    data: { relation: edge.relation },
  }));

  return { nodes, edges };
}

export function graphNeighbors(nodeId: string, edges: EvidenceGraphVisualizationEdge[]): Set<string> {
  const neighbors = new Set([nodeId]);
  for (const edge of edges) {
    if (edge.source === nodeId) neighbors.add(edge.target);
    if (edge.target === nodeId) neighbors.add(edge.source);
  }
  return neighbors;
}
