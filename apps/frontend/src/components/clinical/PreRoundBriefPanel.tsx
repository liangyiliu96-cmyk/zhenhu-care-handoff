import type { ReactNode } from 'react';
import { AlertTriangle, BookOpenCheck, FilePenLine, LoaderCircle, Stethoscope } from 'lucide-react';
import { Box, Button, Card, Chip, Divider, Stack, Typography } from '@mui/material';

export interface PreRoundBrief {
  patient_id: string;
  state_version: number;
  attention_items: Array<{
    kind: string;
    priority: 'high' | 'medium' | 'low' | string;
    title: string;
    action: string;
    facts: Array<{ source_type: string; source_id: string; observed_at?: string; field: string; value: unknown }>;
  }>;
  history_gaps: Array<{ field: string; label: string; status: 'needs_input' | string; prompt: string }>;
}

interface PreRoundBriefPanelProps {
  brief?: PreRoundBrief;
  loading?: boolean;
  generating?: boolean;
  error?: string;
  onGenerateDraft: () => void;
}

export default function PreRoundBriefPanel({ brief, loading = false, generating = false, error, onGenerateDraft }: PreRoundBriefPanelProps) {
  const attention = brief?.attention_items ?? [];
  const gaps = brief?.history_gaps ?? [];
  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Box sx={{ px: 2, py: 1.4, display: 'flex', gap: 1.1, alignItems: 'flex-start', borderBottom: '1px solid', borderColor: 'divider' }}>
      <Box sx={{ width: 34, height: 34, display: 'grid', placeItems: 'center', bgcolor: 'rgba(11, 100, 114, 0.09)', color: 'primary.dark', borderRadius: 1 }}><Stethoscope size={18} /></Box>
      <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="subtitle1">查房前预读</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.2 }}>基于本次已记录的体征、检验和告警整理，进入查房前请先核对。</Typography></Box>
      <Chip size="small" variant="outlined" label={`状态版本 ${brief?.state_version ?? '-'}`} />
    </Box>
    <Box sx={{ p: 1.75, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) minmax(260px, 0.72fr)' }, gap: 2 }}>
      <Box>
        <SectionTitle icon={<AlertTriangle size={16} />} title="本轮需核实" count={attention.length} />
        {loading ? <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>正在整理当前患者事实...</Typography> : attention.length ? <Stack spacing={0.8} sx={{ mt: 1 }}>{attention.map((item, index) => <Box key={`${item.kind}-${index}`} sx={{ pl: 1.1, py: 0.25, borderLeft: '3px solid', borderColor: item.priority === 'high' ? 'error.main' : 'warning.main' }}>
          <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{item.title}</Typography><Chip size="small" label={item.priority === 'high' ? '优先核实' : '待核实'} color={item.priority === 'high' ? 'error' : 'warning'} variant="outlined" /></Box>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>{item.action}</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.55 }}>{item.facts.map((fact, factIndex) => <Chip key={`${fact.source_type}-${fact.source_id}-${factIndex}`} size="small" variant="outlined" label={`来源：${fact.source_type}`} />)}</Box>
        </Box>)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>暂无新的结构化变化，仍请结合原始病历完成查房。</Typography>}
      </Box>
      <Box sx={{ borderLeft: { lg: '1px solid' }, borderColor: 'divider', pl: { lg: 2 } }}>
        <SectionTitle icon={<BookOpenCheck size={16} />} title="病史待补" count={gaps.length} />
        {loading ? null : gaps.length ? <Stack spacing={0.65} sx={{ mt: 1 }}>{gaps.slice(0, 5).map((gap) => <Box key={gap.field}><Chip size="small" label={`待补：${gap.label}`} variant="outlined" /><Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>{gap.prompt}</Typography></Box>)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>核心病史字段已具备，仍可按实际情况补充。</Typography>}
      </Box>
    </Box>
    <Divider />
    <Box sx={{ px: 2, py: 1.15, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', bgcolor: 'rgba(11, 100, 114, 0.025)' }}>
      <Typography variant="caption" color="text.secondary" sx={{ flex: 1, minWidth: 220 }}>草稿仅汇总带来源的客观事实；评估与计划仍需医生填写。</Typography>
      <Button size="small" variant="outlined" startIcon={generating ? <LoaderCircle size={15} /> : <FilePenLine size={15} />} onClick={onGenerateDraft} disabled={loading || generating}>{generating ? '生成中...' : '生成增量病程草稿'}</Button>
    </Box>
    {error ? <Typography variant="caption" color="error" sx={{ display: 'block', px: 2, pb: 1.2 }}>{error}</Typography> : null}
  </Card>;
}

function SectionTitle({ icon, title, count }: { icon: ReactNode; title: string; count: number }) {
  return <Box sx={{ display: 'flex', gap: 0.65, alignItems: 'center' }}>{icon}<Typography variant="subtitle2">{title}</Typography><Chip size="small" label={count} sx={{ height: 20 }} /></Box>;
}
