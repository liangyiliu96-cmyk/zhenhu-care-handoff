import { Alert, Box, Button, Card, Chip, InputAdornment, TextField, Typography } from '@mui/material';
import { AlertTriangle, ArrowRight, ClipboardCheck, Clock3, HeartPulse, Search, UsersRound } from 'lucide-react';
import { useState } from 'react';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { useMonitoringOverdue, useNursePriority, useShiftReport } from '@/hooks/use-nurse-management';
import { useWardTrends } from '@/hooks/use-ward';
import { nursePatientDisplayName, riskLabel, riskColor, formatBp } from '@/utils/nurse-patient-utils';
import type { NurseTask, NurseTasksResponse, NursingTaskItem } from '@/types/nurse-management';

interface NurseWorkspacePanelsProps {
  tasks?: NurseTasksResponse;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onOpenPatient: (patient: NurseTask) => void;
  onRecord: (patient: NurseTask) => void;
  onComplete: (patient: NurseTask, task: NursingTaskItem) => void;
}

export function NurseShiftOverview(props: NurseWorkspacePanelsProps) {
  const priority = useNursePriority(true);
  const overdue = useMonitoringOverdue(true);
  const shift = useShiftReport(true);
  const trends = useWardTrends(true);

  if (props.loading) return <CardSkeleton height={420} />;
  if (props.error) return <ErrorBanner message="班次护理数据加载失败" onRetry={props.onRetry} />;
  const data = props.tasks;
  const patients = data?.tasks ?? [];
  const actionable = patients.filter((patient) => (patient.open_task_count ?? patient.task_items?.length ?? 0) > 0 || patient.alert_count > 0);
  const deteriorating = trends.data?.patients.filter((patient) => ['down', '↓'].includes(patient.spo2_trend) || ['up', '↑'].includes(patient.hr_trend) || patient.alerts > 0) ?? [];

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <Alert severity="info" icon={<ClipboardCheck size={18} />}>{patients.length ? priority.data?.advice ?? '正在生成本班巡查优先级。' : '当前班次没有待执行的责任患者任务；交接、监测和执行统计仍持续更新。'}</Alert>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="在院患者" value={data?.total ?? 0} icon={<UsersRound size={18} />} />
      <Metric label="待执行任务" value={data?.open_task_count ?? 0} icon={<ClipboardCheck size={18} />} tone={(data?.open_task_count ?? 0) ? 'info' : 'default'} />
      <Metric label="体征待测" value={data?.vital_signs_overdue ?? 0} icon={<Clock3 size={18} />} tone={(data?.vital_signs_overdue ?? 0) ? 'warning' : 'default'} />
      <Metric label="患者告警" value={data?.with_alerts ?? 0} icon={<AlertTriangle size={18} />} tone={(data?.with_alerts ?? 0) ? 'error' : 'default'} />
    </Box>
    <NursingTrendBoard patients={patients} totalTasks={data?.open_task_count ?? 0} overdue={data?.vital_signs_overdue ?? 0} deteriorating={deteriorating.length} />
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.25fr) minmax(340px, 0.75fr)' }, gap: 1.5, alignItems: 'start' }}>
      <PriorityQueue patients={actionable} onOpenPatient={props.onOpenPatient} onRecord={props.onRecord} onComplete={props.onComplete} />
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        <MonitoringSnapshot overdue={overdue.data?.total ?? 0} critical={overdue.data?.critical_overdue ?? 0} error={Boolean(overdue.error)} deteriorating={deteriorating} />
        <ShiftSnapshot total={shift.data?.total ?? 0} highFocus={shift.data?.high_focus.length ?? 0} discharge={shift.data?.today_discharge ?? 0} />
      </Box>
    </Box>
  </Box>;
}

export function NursePatientList(props: NurseWorkspacePanelsProps) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'tasks' | 'alerts'>('all');
  const patients = props.tasks?.tasks ?? [];
  const keyword = search.trim().toLowerCase();
  const visible = patients.filter((patient) => {
    const matchesSearch = !keyword || [patient.name, patient.disease, patient.department].some((value) => value.toLowerCase().includes(keyword));
    const matchesFilter = filter === 'all' || filter === 'tasks' && (patient.open_task_count ?? patient.task_items?.length ?? 0) > 0 || filter === 'alerts' && patient.alert_count > 0;
    return matchesSearch && matchesFilter;
  });

  if (props.loading) return <CardSkeleton height={380} />;
  if (props.error) return <ErrorBanner message="在院患者数据加载失败" onRetry={props.onRetry} />;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <TextField size="small" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索患者、病种或科室" sx={{ width: 300, maxWidth: '100%' }} slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> } }} />
      {([['all', '全部患者'], ['tasks', '有待办'], ['alerts', '有告警']] as const).map(([value, label]) => <Chip key={value} label={label} clickable color={filter === value ? 'info' : 'default'} variant={filter === value ? 'filled' : 'outlined'} onClick={() => setFilter(value)} />)}
      <Typography variant="caption" color="text.secondary" sx={{ ml: { lg: 'auto' } }}>显示 {visible.length} / {patients.length} 名患者</Typography>
    </Box>
    {visible.length === 0 ? <EmptyState icon="" title={patients.length ? '没有匹配的患者' : '当前没有可访问的在院患者'} description={patients.length ? '可调整搜索或筛选条件。' : '责任病区或床位分配更新后会自动同步。'} /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1, display: { xs: 'none', lg: 'grid' }, gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(220px, 1fr) minmax(180px, 0.75fr) auto', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><ColumnTitle>患者</ColumnTitle><ColumnTitle>护理状态</ColumnTitle><ColumnTitle>最近监测</ColumnTitle><ColumnTitle align="right">操作</ColumnTitle></Box>
      {visible.map((patient, index) => <PatientRow key={patient.patient_id} patient={patient} last={index === visible.length - 1} onOpen={() => props.onOpenPatient(patient)} onRecord={() => props.onRecord(patient)} />)}
    </Card>}
  </Box>;
}

function NursingTrendBoard({ patients, totalTasks, overdue, deteriorating }: { patients: NurseTask[]; totalTasks: number; overdue: number; deteriorating: number }) {
  const total = patients.length;
  const highRisk = patients.filter((patient) => patient.risk_level === 'high').length;
  const withAlerts = patients.filter((patient) => patient.alert_count > 0).length;
  const focus = [
    { label: '任务积压', value: totalTasks, base: Math.max(total, totalTasks), tone: 'info.main', track: 'info.light' },
    { label: '监测逾期', value: overdue, base: total, tone: 'warning.main', track: 'warning.light' },
    { label: '高风险患者', value: highRisk, base: total, tone: 'error.main', track: 'error.light' },
    { label: '趋势需关注', value: deteriorating || withAlerts, base: total, tone: 'error.main', track: 'error.light' },
  ];
  return <Card variant="outlined" sx={{ overflow: 'hidden' }}>
    <Box sx={{ px: 1.75, py: 1.3, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><HeartPulse size={18} /><Box><Typography variant="subtitle2" fontWeight={600}>班次处置态势</Typography><Typography variant="caption" color="text.secondary">结合任务、逾期、风险和患者趋势安排本班巡查</Typography></Box><Chip size="small" color={overdue || highRisk || deteriorating ? 'warning' : 'success'} label={overdue || highRisk || deteriorating ? '需要关注' : '班次平稳'} sx={{ ml: 'auto' }} /></Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1, px: 1.5, py: 1.25, bgcolor: 'rgba(11, 100, 114, 0.018)' }}>{focus.map((item) => <Box key={item.label} sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', gap: 0.45, alignItems: 'baseline' }}><Typography variant="subtitle2" color={item.tone}>{item.value}</Typography><Typography variant="caption" color="text.secondary">/ {item.base}</Typography></Box><Typography variant="caption" color="text.secondary" noWrap>{item.label}</Typography><Box sx={{ height: 4, borderRadius: 2, bgcolor: item.track, overflow: 'hidden', mt: 0.55 }}><Box sx={{ width: `${item.base ? Math.min(100, Math.round(item.value / item.base * 100)) : 0}%`, height: '100%', borderRadius: 2, bgcolor: item.tone }} /></Box></Box>)}</Box>
  </Card>;
}

function PriorityQueue({ patients, onOpenPatient, onRecord, onComplete }: { patients: NurseTask[]; onOpenPatient: (patient: NurseTask) => void; onRecord: (patient: NurseTask) => void; onComplete: (patient: NurseTask, task: NursingTaskItem) => void }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.2, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><ClipboardCheck size={18} /><Typography variant="subtitle2" fontWeight={600}>本班优先执行</Typography><Chip size="small" label={patients.length} color={patients.length ? 'info' : 'default'} sx={{ ml: 'auto' }} /></Box>{patients.length === 0 ? <Box sx={{ p: 1.75 }}><Typography variant="body2" color="text.secondary">当前没有需要立即处理的护理任务。</Typography></Box> : patients.slice(0, 8).map((patient, index) => <Box key={patient.patient_id} sx={{ px: 1.75, py: 1.25, borderBottom: index === Math.min(patients.length, 8) - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Button size="small" variant="text" sx={{ px: 0, minWidth: 0, fontWeight: 600 }} onClick={() => onOpenPatient(patient)}>{nursePatientDisplayName(patient)}</Button>{patient.alert_count ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}{patient.vital_signs_due ? <Chip size="small" color="warning" variant="outlined" label="体征待测" /> : null}<Typography variant="caption" color="text.secondary">{patient.disease}</Typography></Box><Box sx={{ mt: 0.8, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 1, alignItems: 'center' }}><Typography variant="body2" color="text.secondary">{patient.task_items?.[0]?.title || '查看患者当前护理状态'}</Typography><Box sx={{ display: 'flex', gap: 0.5 }}>{patient.task_items?.[0] ? <Button size="small" color="success" onClick={() => onComplete(patient, patient.task_items![0])}>完成</Button> : null}<Button size="small" variant="outlined" onClick={() => onRecord(patient)}>录护理</Button></Box></Box></Box>)}</Card>;
}

function MonitoringSnapshot({ overdue, critical, error, deteriorating }: { overdue: number; critical: number; error: boolean; deteriorating: Array<{ patient_id: string; name: string; disease: string; alerts: number }> }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><Clock3 size={18} /><Typography variant="subtitle2" fontWeight={600}>监测与风险</Typography><Chip size="small" color={critical ? 'error' : overdue ? 'warning' : 'success'} label={error ? '监测待重试' : `${overdue} 人逾期`} sx={{ ml: 'auto' }} /></Box><Box sx={{ p: 1.5 }}><Typography variant="body2" color="text.secondary">{error ? '逾期服务暂时不可用，护理任务中的体征待测仍可继续处理。' : critical ? `有 ${critical} 名患者超过监测窗口 2 小时以上。` : overdue ? '请先处理监测逾期患者，再完成常规护理任务。' : '当前没有严格逾期的生命体征。'}</Typography>{deteriorating.length ? <Box sx={{ mt: 1.1 }}>{deteriorating.slice(0, 3).map((patient) => <Typography key={patient.patient_id} variant="caption" sx={{ display: 'block', py: 0.3 }}><strong>{patient.name}</strong> · {patient.disease}{patient.alerts ? ` · ${patient.alerts} 条告警` : ''}</Typography>)}</Box> : null}</Box></Card>;
}

function ShiftSnapshot({ total, highFocus, discharge }: { total: number; highFocus: number; discharge: number }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.5, py: 1.15, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><HeartPulse size={18} /><Typography variant="subtitle2" fontWeight={600}>交班状态</Typography><ArrowRight size={16} style={{ marginLeft: 'auto' }} /></Box><Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', p: 1.5, gap: 1 }}><PatientMetric label="在院" value={total} /><PatientMetric label="重点" value={highFocus} tone={highFocus ? 'warning' : 'default'} /><PatientMetric label="今日出院" value={discharge} tone={discharge ? 'info' : 'default'} /></Box></Card>;
}

function PatientRow({ patient, last, onOpen, onRecord }: { patient: NurseTask; last: boolean; onOpen: () => void; onRecord: () => void }) {
  const vitals = patient.latest_vital_values;
  const taskCount = patient.open_task_count ?? patient.task_items?.length ?? 0;
  return <Box sx={{ px: 1.75, py: 1.25, display: { xs: 'flex', lg: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(220px, 1fr) minmax(180px, 0.75fr) auto', gap: { xs: 0.75, lg: 1.5 }, alignItems: 'center', borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}><Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Chip size="small" color={riskColor(patient.risk_level)} label={riskLabel(patient.risk_level)} /></Box><Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department}</Typography></Box><Box><Box sx={{ display: 'flex', gap: 0.6, flexWrap: 'wrap' }}>{taskCount ? <Chip size="small" color="info" label={`${taskCount} 项待办`} /> : <Chip size="small" variant="outlined" label="无待办" />}{patient.vital_signs_due ? <Chip size="small" color="warning" variant="outlined" label="体征待测" /> : null}{patient.alert_count ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>{patient.bedside_flags?.vs_trend || '暂无体征趋势'}{patient.bedside_flags?.fall_risk ? ` · 跌倒风险 ${patient.bedside_flags.fall_risk}` : ''}</Typography></Box><Typography variant="body2" color="text.secondary">BP {formatBp(vitals?.systolic, vitals?.diastolic)} · SpO2 {vitals?.spo2 ?? '--'}%</Typography><Box sx={{ display: 'flex', justifyContent: { xs: 'flex-start', lg: 'flex-end' }, gap: 0.5 }}><Button size="small" onClick={onOpen}>详情</Button><Button size="small" variant="outlined" onClick={onRecord}>录护理</Button></Box></Box>;
}

function Metric({ label, value, icon, tone = 'default' }: { label: string; value: number; icon: React.ReactNode; tone?: 'default' | 'info' | 'warning' | 'error' }) { const color = tone === 'default' ? 'primary' : tone; return <Card variant="outlined" sx={{ p: 1.6, bgcolor: 'background.paper' }}><Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center', color: `${color}.main` }}><Box sx={{ width: 32, height: 32, borderRadius: 1, display: 'grid', placeItems: 'center', bgcolor: `${color}.light` }}>{icon}</Box><Typography variant="caption" color="text.secondary">{label}</Typography></Box><Typography variant="h5" color={tone === 'default' ? 'text.primary' : `${tone}.main`} sx={{ mt: 0.85 }}>{value}</Typography></Card>; }
function PatientMetric({ label, value, tone = 'default' }: { label: string; value: number; tone?: 'default' | 'info' | 'warning' }) { return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={600} color={tone === 'default' ? 'text.primary' : `${tone}.main`}>{value}</Typography></Box>; }
function ColumnTitle({ children, align }: { children: React.ReactNode; align?: 'right' }) { return <Typography variant="caption" color="text.secondary" textAlign={align}>{children}</Typography>; }
