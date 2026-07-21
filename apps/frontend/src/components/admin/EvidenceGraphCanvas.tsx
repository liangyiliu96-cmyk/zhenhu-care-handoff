import { Box, Button, Chip, Divider, Typography, useTheme } from '@mui/material';
import { Background, Controls, MiniMap, ReactFlow, type EdgeMouseHandler, type Node, type NodeMouseHandler, useEdgesState, useNodesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useEffect, useMemo, useState } from 'react';

import type { EvidenceGraphVisualizationEdge, EvidenceGraphVisualizationNode, EvidenceGraphVisualizationResponse } from '@/types/evidence-graph';
import { graphNeighbors, layoutEvidenceGraph, relationLabel, type EvidenceFlowData, type EvidenceFlowEdge, type EvidenceFlowNode } from '@/utils/evidence-graph-layout';

interface EvidenceGraphCanvasProps {
  graph: EvidenceGraphVisualizationResponse;
}

function nodeKindLabel(kind: EvidenceGraphVisualizationNode['kind']) {
  return {
    disease: '病种',
    evidence: '临床证据',
    rule: '临床规则',
    source: '证据来源',
    layer: '知识层',
    department: '适用科室',
  }[kind];
}

function nodeColor(node: Node) {
  const data = node.data as EvidenceFlowData;
  return {
    disease:    '#0B6472',
    evidence:   '#79ADBA',
    rule:       '#75AF92',
    source:     '#D7A664',
    layer:      '#AABBB7',
    department: '#D58B8B',
  }[data.kind] ?? '#B0BEC5';
}

function nodeDetail(node: EvidenceGraphVisualizationNode) {
  if (node.kind === 'evidence') return [node.source, node.category, node.layer, node.version].filter(Boolean).join(' · ');
  if (node.kind === 'rule') return node.key || relationLabel(node.relation || '');
  if (node.kind === 'disease') return [node.department, node.disease_id].filter(Boolean).join(' · ');
  return '';
}

export default function EvidenceGraphCanvas({ graph }: EvidenceGraphCanvasProps) {
  const theme = useTheme();
  const layout = useMemo(() => layoutEvidenceGraph(graph), [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState<EvidenceFlowNode>(layout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<EvidenceFlowEdge>(layout.edges);
  const [selectedNodeId, setSelectedNodeId] = useState(graph.root_id);
  const [selectedEdge, setSelectedEdge] = useState<EvidenceGraphVisualizationEdge | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);

  useEffect(() => {
    setNodes(layout.nodes);
    setEdges(layout.edges);
    setSelectedNodeId(graph.root_id);
    setSelectedEdge(null);
    setFocusId(null);
  }, [graph.root_id, layout.edges, layout.nodes, setEdges, setNodes]);

  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId) ?? graph.nodes.find((node) => node.id === graph.root_id) ?? null;
  const focusNodes = useMemo(() => focusId ? graphNeighbors(focusId, graph.edges) : null, [focusId, graph.edges]);
  const visibleNodes = useMemo(() => nodes.map((node) => ({
    ...node,
    selected: node.id === selectedNode?.id,
    style: {
      ...node.style,
      opacity: focusNodes && !focusNodes.has(node.id) ? 0.24 : 1,
      transition: 'opacity 180ms ease, box-shadow 180ms ease',
      boxShadow: node.id === selectedNode?.id ? `0 0 0 3px ${theme.palette.primary.light}` : 'none',
    },
  })), [focusNodes, nodes, selectedNode?.id, theme.palette.primary.light]);
  const visibleEdges = useMemo(() => edges.map((edge) => ({
    ...edge,
    selected: edge.id === selectedEdge?.id,
    style: {
      ...edge.style,
      opacity: focusNodes && (!focusNodes.has(edge.source) || !focusNodes.has(edge.target)) ? 0.16 : 1,
      stroke: edge.id === selectedEdge?.id ? theme.palette.primary.main : edge.style?.stroke,
      strokeWidth: edge.id === selectedEdge?.id ? 2.25 : edge.style?.strokeWidth,
      transition: 'opacity 180ms ease, stroke 180ms ease',
    },
  })), [edges, focusNodes, selectedEdge?.id, theme.palette.primary.main]);

  const onNodeClick: NodeMouseHandler<EvidenceFlowNode> = (_, node) => {
    setSelectedNodeId(node.id);
    setSelectedEdge(null);
  };
  const onNodeDoubleClick: NodeMouseHandler<EvidenceFlowNode> = (_, node) => {
    setFocusId((current) => current === node.id ? null : node.id);
    setSelectedNodeId(node.id);
    setSelectedEdge(null);
  };
  const onEdgeClick: EdgeMouseHandler<EvidenceFlowEdge> = (_, edge) => {
    setSelectedEdge(graph.edges.find((item) => item.id === edge.id) ?? null);
  };

  return (
    <Box sx={{ mt: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'hidden', bgcolor: 'background.paper' }}>
      <Box sx={{ px: 1.5, py: 1.1, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="subtitle2" fontWeight={700}>可交互知识关系图</Typography>
          <Typography variant="caption" color="text.secondary">拖拽节点调整视图，点击查看详情，双击聚焦一跳关系。</Typography>
        </Box>
        {focusId ? <Button size="small" onClick={() => setFocusId(null)}>恢复全图</Button> : null}
        <Chip size="small" variant="outlined" label={`${graph.nodes.length} 节点 · ${graph.edges.length} 关系`} />
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1fr) 268px' }, minHeight: 430 }}>
        <Box sx={{ minHeight: 520, bgcolor: 'background.default' }}>
          <ReactFlow<EvidenceFlowNode, EvidenceFlowEdge>
            nodes={visibleNodes}
            edges={visibleEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onEdgeClick={onEdgeClick}
            fitView
            fitViewOptions={{ padding: 0.35, maxZoom: 1.2 }}
            minZoom={0.3}
            maxZoom={1.8}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
            defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
          >
            <Background color={theme.palette.divider} gap={18} size={1} />
            <Controls showInteractive={false} />
            <MiniMap nodeColor={nodeColor} maskColor={theme.palette.mode === 'dark' ? 'rgba(7, 14, 16, 0.56)' : 'rgba(243, 246, 245, 0.66)'} />
          </ReactFlow>
        </Box>
        <Box sx={{ p: 1.5, borderTop: { xs: '1px solid', xl: 0 }, borderLeft: { xs: 0, xl: '1px solid' }, borderColor: 'divider', bgcolor: 'background.paper' }}>
          {selectedEdge ? <>
            <Typography variant="caption" color="text.secondary">关系说明</Typography>
            <Typography variant="subtitle2" sx={{ mt: 0.35 }}>{relationLabel(selectedEdge.relation)}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.65 }}>该关系来自 Neo4j 的受控病种子图，可继续点击两端节点查看其证据或规则内容。</Typography>
            <Divider sx={{ my: 1.5 }} />
          </> : null}
          {selectedNode ? <>
            <Chip size="small" label={nodeKindLabel(selectedNode.kind)} color={selectedNode.kind === 'rule' ? 'success' : selectedNode.kind === 'evidence' ? 'info' : 'default'} variant="outlined" />
            <Typography variant="subtitle2" sx={{ mt: 0.8, overflowWrap: 'anywhere' }}>{selectedNode.label}</Typography>
            {nodeDetail(selectedNode) ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.35, lineHeight: 1.5 }}>{nodeDetail(selectedNode)}</Typography> : null}
            {(selectedNode.text || selectedNode.content) ? <Typography variant="body2" sx={{ mt: 1.15, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{selectedNode.text || selectedNode.content}</Typography> : <Typography variant="body2" color="text.secondary" sx={{ mt: 1.15, lineHeight: 1.65 }}>选择证据或规则节点后，可在这里查看其来源、版本与关联内容。</Typography>}
          </> : null}
        </Box>
      </Box>
    </Box>
  );
}
