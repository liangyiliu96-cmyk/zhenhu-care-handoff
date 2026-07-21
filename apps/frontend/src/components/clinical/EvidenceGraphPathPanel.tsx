import { Alert, Box, Card, Chip, CircularProgress, Divider, Typography } from '@mui/material';
import { BookOpenCheck, Network } from 'lucide-react';

import { usePatientEvidenceGraph } from '@/hooks/use-patient-dashboard';
import type { EvidenceGraphRule } from '@/types/evidence-graph';

interface EvidenceGraphPathPanelProps {
  patientId: string;
  compact?: boolean;
  framed?: boolean;
}

const RULE_META: Record<string, { label: string; color: 'success' | 'info' | 'warning' | 'default' }> = {
  HAS_DISCHARGE_CRITERION: { label: '出院标准', color: 'success' },
  HAS_MEDICATION_RULE: { label: '用药规则', color: 'info' },
  HAS_MONITORING_RULE: { label: '监测重点', color: 'warning' },
  HAS_CARE_TASK: { label: '护理与随访', color: 'default' },
};

export default function EvidenceGraphPathPanel({ patientId, compact = false, framed = true }: EvidenceGraphPathPanelProps) {
  const graph = usePatientEvidenceGraph(patientId);
  const data = graph.data;
  const ruleLimit = compact ? 3 : 6;
  const evidenceLimit = compact ? 2 : 4;

  const content = <>
    <PanelHeading diseaseId={data?.disease_id} />
    {graph.isLoading ? <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1.25 }}><CircularProgress size={18} /><Typography variant="body2" color="text.secondary">正在加载路径证据...</Typography></Box> : null}
    {graph.error ? <Alert severity="warning" sx={{ mt: 1 }}>路径证据暂时不可用，不影响现有诊疗流程。</Alert> : null}
    {!graph.isLoading && !graph.error && data && !data.available ? <Alert severity="info" sx={{ mt: 1 }}>{data.reason || '当前患者尚无可用的图谱路径。'}</Alert> : null}
    {data?.available ? <>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mt: 1.15 }}>
        {data.rules.slice(0, ruleLimit).map((rule, index) => <RuleRow key={`${rule.relation}:${rule.key}:${index}`} rule={rule} />)}
      </Box>
      {data.evidence.length ? <>
        <Divider sx={{ my: 1.25 }} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mb: 0.75 }}><BookOpenCheck size={15} /><Typography variant="caption" color="text.secondary" fontWeight={700}>关联证据来源</Typography></Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.7 }}>
          {data.evidence.slice(0, evidenceLimit).map((evidence) => <Box key={evidence.id} sx={{ pl: 1, borderLeft: '2px solid', borderColor: 'info.light' }}><Typography variant="caption" fontWeight={700} display="block">{evidence.topic}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.15 }}>{evidence.layer} · {evidence.source}</Typography></Box>)}
        </Box>
      </> : null}
    </> : null}
  </>;

  if (!framed) return <Box>{content}</Box>;
  return <Card variant="outlined" sx={{ overflow: 'hidden', bgcolor: 'background.paper' }}><Box sx={{ p: 1.6 }}>{content}</Box></Card>;
}

function PanelHeading({ diseaseId }: { diseaseId?: string }) {
  return <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.85 }}><Box sx={{ width: 30, height: 30, borderRadius: 1, display: 'grid', placeItems: 'center', bgcolor: 'primary.light', color: 'primary.dark' }}><Network size={16} /></Box><Box sx={{ minWidth: 0 }}><Typography variant="subtitle2" fontWeight={700}>路径证据</Typography><Typography variant="caption" color="text.secondary">{diseaseId ? `${diseaseId} · 图谱关联规则` : '图谱关联规则与引用来源'}</Typography></Box></Box>;
}

function RuleRow({ rule }: { rule: EvidenceGraphRule }) {
  const meta = RULE_META[rule.relation] ?? { label: '临床规则', color: 'default' as const };
  return <Box sx={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: 0.75, alignItems: 'start' }}><Chip size="small" color={meta.color} variant={meta.color === 'default' ? 'outlined' : 'filled'} label={meta.label} /><Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={600}>{rule.content}</Typography>{rule.key && rule.key !== rule.content ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.2 }}>{rule.key}</Typography> : null}</Box></Box>;
}
