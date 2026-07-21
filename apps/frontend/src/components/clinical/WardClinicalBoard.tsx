import { useState } from 'react';
import { Alert, Box, Button, Card, Chip, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { Activity, AlertTriangle, ArrowDown, ArrowRight, ArrowUp, ClipboardList, FlaskConical, ListOrdered, RefreshCw } from 'lucide-react';
import { useMutation } from '@tanstack/react-query';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { useWardLabSummary, useWardPriority, useWardTrends, useWardVisitOrder, useWardVitals } from '@/hooks/use-ward';
import { fetchWardPriority } from '@/services/ward-service';
import type { WardAbnormalLab, WardPriorityPatient, WardPriorityResponse, WardTrendPatient, WardVitalMetric, WardVitalPatient, WardVisitPatient } from '@/types/ward';

interface WardClinicalBoardProps {
  onOpenPatient: (patientId: string) => void;
}

const VITAL_OPTIONS: Array<{ value: WardVitalMetric; label: string; unit: string }> = [
  { value: 'spo2', label: 'SpO2', unit: '%' },
  { value: 'systolic', label: '血压', unit: 'mmHg' },
  { value: 'heart_rate', label: '心率', unit: 'bpm' },
  { value: 'temperature', label: '体温', unit: 'C' },
];

export default function WardClinicalBoard({ onOpenPatient }: WardClinicalBoardProps) {
  const [metric, setMetric] = useState<WardVitalMetric>('spo2');
  const vitals = useWardVitals(metric);
  const trends = useWardTrends();
  const visitOrder = useWardVisitOrder();
  const priority = useWardPriority();
  const labs = useWardLabSummary();

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <VisitOrderPanel query={visitOrder} onOpenPatient={onOpenPatient} />
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 0.9fr) minmax(0, 1.1fr)' }, gap: 2, alignItems: 'start' }}>
      <VitalComparisonPanel metric={metric} query={vitals} onMetricChange={setMetric} onOpenPatient={onOpenPatient} />
      <TrendsPanel query={trends} onOpenPatient={onOpenPatient} />
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 0.8fr) minmax(0, 1.2fr)' }, gap: 2, alignItems: 'start' }}>
      <PriorityPanel query={priority} onOpenPatient={onOpenPatient} />
      <LabSummaryPanel query={labs} onOpenPatient={onOpenPatient} />
    </Box>
  </Box>;
}

function VisitOrderPanel({ query, onOpenPatient }: { query: ReturnType<typeof useWardVisitOrder>; onOpenPatient: (patientId: string) => void }) {
  if (query.isLoading) return <CardSkeleton height={180} />;
  if (query.error || !query.data) return <ErrorBanner message="查房顺序加载失败" onRetry={() => void query.refetch()} />;
  const data = query.data;
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <ClipboardList size={18} /><Typography variant="subtitle2" fontWeight={600}>查房优先顺序</Typography>
      <Chip size="small" color={data.urgent ? 'error' : 'default'} label={`紧急 ${data.urgent}`} sx={{ ml: 'auto' }} />
      <Chip size="small" variant="outlined" label={`稳定 ${data.stable}`} />
    </Box>
    <Box sx={{ px: 1.75, py: 1.15 }}><Alert severity="info" icon={false} sx={{ py: 0.25 }}>{data.reason}</Alert></Box>
    {data.visit_order.length === 0 ? <EmptyState icon="" title="暂无在院患者" /> : <Box>{data.visit_order.slice(0, 6).map((patient, index) => <VisitRow key={patient.patient_id} patient={patient} index={index} onOpenPatient={onOpenPatient} />)}</Box>}
  </Card>;
}

function VisitRow({ patient, index, onOpenPatient }: { patient: WardVisitPatient; index: number; onOpenPatient: (patientId: string) => void }) {
  const urgent = patient.deteriorating || (patient.news2 ?? 0) >= 5 || patient.alerts > 0;
  return <Button key={patient.patient_id} color="inherit" onClick={() => onOpenPatient(patient.patient_id)} sx={{ width: '100%', minHeight: 48, px: 1.75, justifyContent: 'flex-start', textAlign: 'left', borderRadius: 0, borderTop: '1px solid', borderColor: 'divider', textTransform: 'none' }}>
    <Box sx={{ width: 24, color: urgent ? 'error.main' : 'text.secondary', fontWeight: 700 }}>{index + 1}</Box>
    <Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="body2" fontWeight={600} noWrap>{patient.name}</Typography><Typography variant="caption" color="text.secondary">NEWS2 {patient.news2 ?? '未评分'} · SpO2 {patient.spo2 ?? '—'}% · 心率 {patient.hr ?? '—'}</Typography></Box>
    <Box sx={{ display: 'flex', gap: 0.5, ml: 1 }}>{patient.deteriorating ? <Chip size="small" color="error" label="恶化" /> : null}{patient.has_pending ? <Chip size="small" color="info" label="待审" /> : null}{patient.alerts ? <Chip size="small" color="warning" label={`${patient.alerts} 告警`} /> : null}</Box>
  </Button>;
}

function VitalComparisonPanel({ metric, query, onMetricChange, onOpenPatient }: { metric: WardVitalMetric; query: ReturnType<typeof useWardVitals>; onMetricChange: (metric: WardVitalMetric) => void; onOpenPatient: (patientId: string) => void }) {
  const selected = VITAL_OPTIONS.find((option) => option.value === metric)!;
  if (query.isLoading) return <CardSkeleton height={300} />;
  if (query.error || !query.data) return <ErrorBanner message="病区体征对比加载失败" onRetry={() => void query.refetch()} />;
  const data = query.data;
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, pt: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Activity size={18} /><Typography variant="subtitle2" fontWeight={600}>体征对比</Typography><Typography variant="caption" color="text.secondary">恶化 {data.summary.declining}</Typography></Box>
    <ToggleButtonGroup exclusive value={metric} size="small" onChange={(_, value: WardVitalMetric | null) => { if (value) onMetricChange(value); }} sx={{ px: 1.25, py: 1 }}>
      {VITAL_OPTIONS.map((option) => <ToggleButton key={option.value} value={option.value}>{option.label}</ToggleButton>)}
    </ToggleButtonGroup>
    {data.patients.length === 0 ? <EmptyState icon="" title="暂无可比较体征" /> : <Box>{data.patients.slice(0, 8).map((patient) => <VitalRow key={patient.patient_id} patient={patient} unit={selected.unit} onOpenPatient={onOpenPatient} />)}</Box>}
  </Card>;
}

function VitalRow({ patient, unit, onOpenPatient }: { patient: WardVitalPatient; unit: string; onOpenPatient: (patientId: string) => void }) {
  const values = patient.vital_values.map((value) => value == null ? '—' : String(value));
  return <Button color="inherit" onClick={() => onOpenPatient(patient.patient_id)} sx={{ width: '100%', px: 1.75, py: 1.05, justifyContent: 'flex-start', textAlign: 'left', borderRadius: 0, borderTop: '1px solid', borderColor: 'divider', textTransform: 'none' }}>
    <TrendIcon trend={patient.trend} /><Box sx={{ minWidth: 0, flex: 1, ml: 0.75 }}><Typography variant="body2" noWrap>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease}</Typography></Box><Typography variant="caption" sx={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{values.join(' / ')} {unit}</Typography>
  </Button>;
}

function TrendsPanel({ query, onOpenPatient }: { query: ReturnType<typeof useWardTrends>; onOpenPatient: (patientId: string) => void }) {
  if (query.isLoading) return <CardSkeleton height={300} />;
  if (query.error || !query.data) return <ErrorBanner message="病区趋势加载失败" onRetry={() => void query.refetch()} />;
  const data = query.data;
  return <Card variant="outlined" sx={{ borderRadius: 1, overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><AlertTriangle size={18} /><Typography variant="subtitle2" fontWeight={600}>病区趋势</Typography><Chip size="small" color={data.deteriorating ? 'warning' : 'success'} label={`${data.deteriorating} 例恶化`} sx={{ ml: 'auto' }} /></Box>
    <TrendPulse total={data.total} deteriorating={data.deteriorating} patients={data.patients} />
    {data.patients.length === 0 ? <EmptyState icon="" title="暂无趋势数据" /> : <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', '& th, & td': { px: 1.25, py: 0.85, fontSize: 12, borderBottom: '1px solid', borderColor: 'divider', textAlign: 'left', whiteSpace: 'nowrap' }, '& th': { color: 'text.secondary', fontWeight: 500, bgcolor: 'background.default' }, '& tbody tr': { cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }, '& tr:last-child td': { borderBottom: 0 } }}><thead><tr><th>患者</th><th>血压</th><th>SpO2</th><th>心率</th><th>体温</th><th>告警</th></tr></thead><tbody>{data.patients.slice(0, 8).map((patient) => <TrendRow key={patient.patient_id} patient={patient} onOpenPatient={onOpenPatient} />)}</tbody></Box>}
  </Card>;
}

function TrendPulse({ total, deteriorating, patients }: { total: number; deteriorating: number; patients: WardTrendPatient[] }) {
  const withAlerts = patients.filter((patient) => patient.alerts > 0).length;
  const withRounds = patients.filter((patient) => patient.round > 0).length;
  const withVitals = patients.filter((patient) => patient.spo2 !== '?' || patient.hr !== '?' || patient.bp_sys !== '?/?').length;
  const items = [
    { label: '恶化趋势', value: deteriorating, tone: 'error.main', track: 'error.light' },
    { label: '伴随告警', value: withAlerts, tone: 'warning.main', track: 'warning.light' },
    { label: '已完成查房', value: withRounds, tone: 'success.main', track: 'success.light' },
    { label: '已有体征记录', value: withVitals, tone: 'info.main', track: 'info.light' },
  ];
  return <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1, px: 1.5, py: 1.25, borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'rgba(11, 100, 114, 0.018)' }}>
    {items.map((item) => <Box key={item.label} sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.45 }}><Typography variant="subtitle2" color={item.tone}>{item.value}</Typography><Typography variant="caption" color="text.secondary">/ {total}</Typography></Box><Typography variant="caption" color="text.secondary" noWrap>{item.label}</Typography><Box sx={{ height: 4, borderRadius: 2, bgcolor: item.track, overflow: 'hidden', mt: 0.55 }}><Box sx={{ height: '100%', width: `${total ? Math.min(100, Math.round(item.value / total * 100)) : 0}%`, bgcolor: item.tone, borderRadius: 2 }} /></Box></Box>)}
  </Box>;
}

function PriorityPanel({ query, onOpenPatient }: { query: ReturnType<typeof useWardPriority>; onOpenPatient: (patientId: string) => void }) {
  const digest = useMutation<WardPriorityResponse>({ mutationFn: () => fetchWardPriority(true) });
  if (query.isLoading) return <CardSkeleton height={220} />;
  if (query.error || !query.data) return <ErrorBanner message="病区重点关注加载失败" onRetry={() => void query.refetch()} />;
  const data = query.data;
  const reasoning = digest.data?.reasoning || data.reasoning;
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <ListOrdered size={18} /><Typography variant="subtitle2" fontWeight={600}>重点关注</Typography>
      <Chip size="small" color={data.top_patients.length ? 'warning' : 'default'} label={`前 ${data.top_patients.length} 位`} sx={{ ml: 'auto' }} />
      <Button size="small" variant="text" disabled={digest.isPending} startIcon={digest.isPending ? <RefreshCw size={14} /> : undefined} onClick={() => digest.mutate()}>告警归并</Button>
    </Box>
    {reasoning ? <Box sx={{ px: 1.75, pt: 1 }}><Typography variant="caption" color="text.secondary">{digest.data ? 'AI 告警归并说明：' : ''}{reasoning}</Typography></Box> : null}
    {digest.error ? <Alert severity="warning" sx={{ mx: 1.5, mt: 1 }}>归并说明暂时不可用，当前仍按规则顺序展示。</Alert> : null}
    {data.top_patients.length === 0 ? <EmptyState icon="" title="暂无需要优先关注的患者" /> : <Box sx={{ pt: reasoning ? 0.75 : 0 }}>{data.top_patients.map((patient, index) => <PriorityRow key={patient.patient_id} patient={patient} index={index} onOpenPatient={onOpenPatient} />)}</Box>}
  </Card>;
}

function PriorityRow({ patient, index, onOpenPatient }: { patient: WardPriorityPatient; index: number; onOpenPatient: (patientId: string) => void }) {
  const highRisk = ['high', '高'].includes(String(patient.risk ?? '').toLowerCase());
  return <Button color="inherit" onClick={() => onOpenPatient(patient.patient_id)} sx={{ width: '100%', px: 1.75, py: 1.05, justifyContent: 'flex-start', textAlign: 'left', borderRadius: 0, borderTop: '1px solid', borderColor: 'divider', textTransform: 'none' }}>
    <Typography variant="body2" fontWeight={700} sx={{ width: 24, color: index === 0 ? 'error.main' : 'text.secondary' }}>{index + 1}</Typography>
    <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" fontWeight={600} noWrap>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease} · NEWS2 {patient.news2 ?? '未评分'}</Typography></Box>
    <Box sx={{ display: 'flex', gap: 0.5, ml: 1 }}>{highRisk ? <Chip size="small" color="error" label="高风险" /> : null}{patient.alerts ? <Chip size="small" color="warning" label={`${patient.alerts} 告警`} /> : null}</Box>
  </Button>;
}

function LabSummaryPanel({ query, onOpenPatient }: { query: ReturnType<typeof useWardLabSummary>; onOpenPatient: (patientId: string) => void }) {
  if (query.isLoading) return <CardSkeleton height={220} />;
  if (query.error || !query.data) return <ErrorBanner message="病区检验异常加载失败" onRetry={() => void query.refetch()} />;
  const data = query.data;
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <FlaskConical size={18} /><Typography variant="subtitle2" fontWeight={600}>检验异常</Typography>
      <Chip size="small" color={data.total ? 'warning' : 'success'} label={`${data.patients_affected} 名患者`} sx={{ ml: 'auto' }} />
    </Box>
    {data.abnormal_labs.length === 0 ? <EmptyState icon="" title="暂无异常检验结果" /> : <Box>{data.abnormal_labs.slice(0, 6).map((lab) => <LabRow key={`${lab.patient_id}:${lab.lab_name}`} lab={lab} onOpenPatient={onOpenPatient} />)}</Box>}
  </Card>;
}

function LabRow({ lab, onOpenPatient }: { lab: WardAbnormalLab; onOpenPatient: (patientId: string) => void }) {
  const high = lab.direction === 'high';
  return <Button color="inherit" onClick={() => onOpenPatient(lab.patient_id)} sx={{ width: '100%', px: 1.75, py: 1.05, justifyContent: 'flex-start', textAlign: 'left', borderRadius: 0, borderTop: '1px solid', borderColor: 'divider', textTransform: 'none' }}>
    <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" fontWeight={600} noWrap>{lab.patient_name}</Typography><Typography variant="caption" color="text.secondary">{lab.lab_name} · 参考 {lab.ref_range}</Typography></Box>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, ml: 1 }}><Typography variant="body2" fontFamily="var(--font-mono)">{lab.value} {lab.unit}</Typography><Chip size="small" color={high ? 'error' : 'info'} label={high ? '偏高' : '偏低'} /></Box>
  </Button>;
}

function TrendRow({ patient, onOpenPatient }: { patient: WardTrendPatient; onOpenPatient: (patientId: string) => void }) {
  return <tr onClick={() => onOpenPatient(patient.patient_id)}><td><Typography variant="body2" noWrap>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease}</Typography></td><td>{patient.bp_sys} <TrendGlyph value={patient.bp_trend} /></td><td>{patient.spo2} <TrendGlyph value={patient.spo2_trend} /></td><td>{patient.hr} <TrendGlyph value={patient.hr_trend} /></td><td>{patient.temp} <TrendGlyph value={patient.temp_trend} /></td><td>{patient.alerts ? <Chip size="small" color="warning" label={patient.alerts} /> : '—'}</td></tr>;
}

function TrendIcon({ trend }: { trend: WardVitalPatient['trend'] }) { return trend === 'declining' ? <ArrowDown size={16} color="#b33b3b" /> : trend === 'improving' ? <ArrowUp size={16} color="#2e7d32" /> : <ArrowRight size={16} color="#6a6a6a" />; }
function TrendGlyph({ value }: { value: string }) { return value === '↓' ? <Box component="span" sx={{ color: 'error.main' }}>↓</Box> : value === '↑' ? <Box component="span" sx={{ color: 'success.main' }}>↑</Box> : <Box component="span" color="text.secondary">{value}</Box>; }
