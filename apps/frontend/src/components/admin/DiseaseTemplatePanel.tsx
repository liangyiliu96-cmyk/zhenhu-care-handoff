import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, InputAdornment, TextField, Typography } from '@mui/material';
import { Activity, Files, Search, ShieldCheck } from 'lucide-react';
import { useMemo, useState } from 'react';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { useDiseaseTemplateDetail, useDiseaseTemplates } from '@/hooks/use-admin';
import type { DiseaseTemplate } from '@/types/admin';

export default function DiseaseTemplatePanel() {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<DiseaseTemplate | null>(null);
  const templates = useDiseaseTemplates();
  const detail = useDiseaseTemplateDetail(selected?.disease_id);
  const visible = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return (templates.data?.templates ?? []).filter((template) => !keyword || [template.disease_id, template.name, template.department].some((value) => value.toLowerCase().includes(keyword)));
  }, [search, templates.data]);
  const departments = new Set((templates.data?.templates ?? []).map((template) => template.department).filter(Boolean));

  if (templates.isLoading) return <CardSkeleton height={300} />;
  if (templates.error || !templates.data) return <ErrorBanner message="病种模板库存加载失败" onRetry={() => void templates.refetch()} />;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))' }, gap: 1.25 }}>
      <Metric label="已部署模板" value={templates.data.count} />
      <Metric label="覆盖科室" value={departments.size} />
      <Metric label="当前匹配" value={visible.length} />
    </Box>
    <TextField size="small" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="按模板名称、病种标识或科室搜索" fullWidth slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> } }} />
    {visible.length === 0 ? <EmptyState icon="" title={search.trim() ? '没有匹配的病种模板' : '尚未部署病种模板'} description={search.trim() ? '可调整搜索条件后重试。' : '模板由后端种子与受审计运维流程管理。'} /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1, display: { xs: 'none', md: 'grid' }, gridTemplateColumns: 'minmax(220px, 1fr) minmax(160px, 0.6fr) minmax(160px, 0.6fr) auto', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><ColumnTitle>病种模板</ColumnTitle><ColumnTitle>适用科室</ColumnTitle><ColumnTitle>最近更新</ColumnTitle><ColumnTitle>临床路径</ColumnTitle></Box>
      {visible.map((template, index) => <Box key={template.disease_id} sx={{ px: 1.75, py: 1.25, display: { xs: 'flex', md: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(220px, 1fr) minmax(160px, 0.6fr) minmax(160px, 0.6fr) auto', gap: { xs: 0.6, md: 1.5 }, alignItems: 'center', borderBottom: index === visible.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}><Files size={17} /><Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={600}>{template.name || template.disease_id}</Typography><Typography variant="caption" color="text.secondary">{template.disease_id}</Typography></Box></Box><Chip size="small" variant="outlined" label={template.department || '未指定科室'} sx={{ justifySelf: 'start' }} /><Typography variant="body2" color="text.secondary">{formatTimestamp(template.updated_at)}</Typography><Button size="small" variant="outlined" onClick={() => setSelected(template)}>查看路径</Button></Box>)}
    </Card>}
    <TemplateDetailDialog template={selected} loading={detail.isLoading} error={detail.error} data={detail.data} onClose={() => setSelected(null)} onRetry={() => void detail.refetch()} />
  </Box>;
}

function TemplateDetailDialog({ template, loading, error, data, onClose, onRetry }: { template: DiseaseTemplate | null; loading: boolean; error: unknown; data: ReturnType<typeof useDiseaseTemplateDetail>['data']; onClose: () => void; onRetry: () => void }) {
  return <Dialog open={Boolean(template)} onClose={onClose} fullWidth maxWidth="md"><DialogTitle>{template?.name || '病种模板'} · 临床路径</DialogTitle><DialogContent dividers>{loading ? <Typography color="text.secondary">正在读取模板路径...</Typography> : error || !data ? <Alert severity="warning" action={<Button color="inherit" size="small" onClick={onRetry}>重试</Button>}>模板路径暂时无法加载。</Alert> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <Alert severity="info" icon={<ShieldCheck size={18} />}>模板用于新入院患者的采集、监测和交接参考，不会修改已在院患者的病程。{data.requires_doctor_review ? ' 关键临床决策仍需医生审核。' : ''}</Alert>
    <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}><Chip size="small" label={data.department || '未指定科室'} /><Chip size="small" color="info" variant="outlined" label={`监测间隔 ${data.monitoring_interval_hours ?? '未配置'} 小时`} /><Chip size="small" variant="outlined" label={`风险因素 ${data.risk_factors.length} 项`} /></Box>
    <PathSection title="监测与预警" icon={<Activity size={17} />} empty="未配置监测指标">{data.vital_signs.map((item, index) => <Box key={`${item.name}-${index}`} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, py: 0.65, borderBottom: '1px solid', borderColor: 'divider' }}><Typography variant="body2">{item.name || '未命名指标'}{item.unit ? ` (${item.unit})` : ''}</Typography><Typography variant="caption" color="text.secondary">{item.alert_if || [item.alert_below != null ? `低于 ${item.alert_below}` : '', item.alert_above != null ? `高于 ${item.alert_above}` : ''].filter(Boolean).join('；') || '常规观察'}</Typography></Box>)}</PathSection>
    <PathSection title="出院条件" icon={<ShieldCheck size={17} />} empty="未配置出院条件">{data.discharge_criteria.map((item, index) => <Box key={`${item.condition}-${index}`} sx={{ py: 0.55 }}><Typography variant="body2">{item.description || item.condition || '未命名条件'}</Typography></Box>)}</PathSection>
    <PathSection title="交接与随访重点" icon={<Files size={17} />} empty="未配置交接或随访内容">{[...data.handoff_instructions.map((item) => item.content), ...data.followup_questions.map((item) => item.question)].filter(Boolean).slice(0, 10).map((item, index) => <Typography key={`${item}-${index}`} variant="body2" sx={{ py: 0.55 }}>{item}</Typography>)}</PathSection>
  </Box>}</DialogContent><DialogActions><Button onClick={onClose}>关闭</Button></DialogActions></Dialog>;
}

function PathSection({ title, icon, empty, children }: { title: string; icon: React.ReactNode; empty: string; children: React.ReactNode[] }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 0.7, borderBottom: '1px solid', borderColor: 'divider' }}>{icon}<Typography variant="subtitle2" fontWeight={600}>{title}</Typography></Box><Box sx={{ px: 1.5, py: 0.7 }}>{children.length ? children : <Typography variant="body2" color="text.secondary">{empty}</Typography>}</Box></Card>;
}

function Metric({ label, value }: { label: string; value: number }) { return <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h5" sx={{ mt: 0.5 }}>{value}</Typography></Card>; }
function ColumnTitle({ children }: { children: React.ReactNode }) { return <Typography variant="caption" color="text.secondary">{children}</Typography>; }
function formatTimestamp(value?: string | number | null) {
  if (value == null || value === '') return '未记录';
  const numericValue = typeof value === 'number' ? value : Number(value);
  const date = Number.isFinite(numericValue)
    ? new Date(numericValue < 10_000_000_000 ? numericValue * 1000 : numericValue)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false });
}
