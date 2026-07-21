import { Alert, Box, Button, Card, Chip, InputAdornment, MenuItem, TextField, Typography } from '@mui/material';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { usePatientDirectory } from '@/hooks/use-patient-directory';
import type { NursePatientDetail, NurseTask, NurseTasksResponse } from '@/types/nurse-management';
import type { PatientDirectoryPatient, PatientDirectoryPhase, PatientDirectorySort } from '@/types/ward';
import { directoryPatientToNurseDetail, riskLabel, riskColor, formatBp } from '@/utils/nurse-patient-utils';

interface NursePatientDirectoryPanelProps {
  tasks?: NurseTasksResponse;
  tasksError: unknown;
  onOpenPatient: (patient: NursePatientDetail) => void;
  onRecord: (patient: NurseTask) => void;
}

const PAGE_SIZE = 20;

export default function NursePatientDirectoryPanel({ tasks, tasksError, onOpenPatient, onRecord }: NursePatientDirectoryPanelProps) {
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState<PatientDirectoryPhase | ''>('');
  const [risk, setRisk] = useState<'low' | 'medium' | 'high' | ''>('');
  const [sort, setSort] = useState<PatientDirectorySort>('risk');
  const [attention, setAttention] = useState<'all' | 'tasks' | 'alerts'>('all');
  const [offset, setOffset] = useState(0);
  const deferredSearch = useDeferredValue(search);
  const directory = usePatientDirectory({ search: deferredSearch, phase: phase || undefined, risk_level: risk || undefined, sort, limit: PAGE_SIZE, offset });
  const taskById = useMemo(() => new Map((tasks?.tasks ?? []).map((task) => [task.patient_id, task])), [tasks]);

  useEffect(() => setOffset(0), [deferredSearch, phase, risk, sort]);

  if (directory.isLoading) return <CardSkeleton height={380} />;
  if (directory.error || !directory.data) return <ErrorBanner message="在院患者目录加载失败" onRetry={() => void directory.refetch()} />;

  const { patients, pagination, total } = directory.data;
  const detailedPatients = patients.map((patient) => asNursingPatient(patient, taskById.get(patient.patient_id)));
  const visible = detailedPatients.filter((patient) => attention === 'all' || attention === 'tasks' && (patient.open_task_count ?? patient.task_items?.length ?? 0) > 0 || attention === 'alerts' && patient.alert_count > 0);
  const start = total === 0 ? 0 : pagination.offset + 1;
  const end = pagination.offset + patients.length;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
    {tasksError ? <Alert severity="warning">护理任务服务暂不可用。患者目录和只读详情仍可查询，护理录入已暂时禁用。</Alert> : null}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(260px, 1fr) 140px 140px 130px' }, gap: 1 }}>
      <TextField size="small" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索患者、病种或病历号" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16} /></InputAdornment> } }} />
      <TextField select size="small" label="阶段" value={phase} onChange={(event) => setPhase(event.target.value as PatientDirectoryPhase | '')}><MenuItem value="">全部阶段</MenuItem><MenuItem value="admission">入院</MenuItem><MenuItem value="monitoring">住院监测</MenuItem><MenuItem value="discharge">出院</MenuItem><MenuItem value="review">审核</MenuItem><MenuItem value="confirm">确认</MenuItem></TextField>
      <TextField select size="small" label="风险" value={risk} onChange={(event) => setRisk(event.target.value as typeof risk)}><MenuItem value="">全部风险</MenuItem><MenuItem value="high">高风险</MenuItem><MenuItem value="medium">中风险</MenuItem><MenuItem value="low">低风险</MenuItem></TextField>
      <TextField select size="small" label="排序" value={sort} onChange={(event) => setSort(event.target.value as PatientDirectorySort)}><MenuItem value="risk">风险优先</MenuItem><MenuItem value="phase">阶段</MenuItem><MenuItem value="name">姓名</MenuItem></TextField>
    </Box>
    <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
      {([['all', '全部患者'], ['tasks', '有待办'], ['alerts', '有告警']] as const).map(([value, label]) => <Chip key={value} size="small" label={label} clickable color={attention === value ? 'info' : 'default'} variant={attention === value ? 'filled' : 'outlined'} onClick={() => setAttention(value)} />)}
      <Typography variant="caption" color="text.secondary" sx={{ ml: { lg: 'auto' } }}>当前页 {visible.length} 名，目录共 {total} 名</Typography>
    </Box>
    {visible.length === 0 ? <EmptyState icon="" title={patients.length ? '当前页没有匹配的患者' : '当前没有可访问的在院患者'} description={patients.length ? '可调整待办、告警筛选或查看下一页。' : '责任病区或床位分配更新后会自动同步。'} /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1, display: { xs: 'none', lg: 'grid' }, gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(220px, 1fr) minmax(180px, 0.75fr) auto', gap: 1.5, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><ColumnTitle>患者</ColumnTitle><ColumnTitle>护理状态</ColumnTitle><ColumnTitle>最近监测</ColumnTitle><ColumnTitle align="right">操作</ColumnTitle></Box>
      {visible.map((patient, index) => <PatientRow key={patient.patient_id} patient={patient} last={index === visible.length - 1} onOpen={() => onOpenPatient(patient)} onRecord={patient.writable ? () => onRecord(toNurseTask(patient)) : undefined} />)}
    </Card>}
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}><Typography variant="caption" color="text.secondary">显示 {start}-{end} / {total} 名患者</Typography><Box sx={{ display: 'flex', gap: 0.5 }}><Button size="small" startIcon={<ChevronLeft size={15} />} disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>上一页</Button><Button size="small" endIcon={<ChevronRight size={15} />} disabled={!pagination.has_more} onClick={() => setOffset((value) => value + PAGE_SIZE)}>下一页</Button></Box></Box>
  </Box>;
}

function PatientRow({ patient, last, onOpen, onRecord }: { patient: NursePatientDetail; last: boolean; onOpen: () => void; onRecord?: () => void }) {
  const vitals = patient.latest_vital_values;
  const taskCount = patient.open_task_count ?? patient.task_items?.length ?? 0;
  return <Box sx={{ px: 1.75, py: 1.25, display: { xs: 'flex', lg: 'grid' }, flexDirection: 'column', gridTemplateColumns: 'minmax(200px, 0.8fr) minmax(220px, 1fr) minmax(180px, 0.75fr) auto', gap: { xs: 0.75, lg: 1.5 }, alignItems: 'center', borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}><Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Chip size="small" color={riskColor(patient.risk_level)} label={riskLabel(patient.risk_level)} /></Box><Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department}</Typography></Box><Box><Box sx={{ display: 'flex', gap: 0.6, flexWrap: 'wrap' }}>{taskCount ? <Chip size="small" color="info" label={`${taskCount} 项待办`} /> : <Chip size="small" variant="outlined" label="无待办" />}{patient.vital_signs_due ? <Chip size="small" color="warning" variant="outlined" label="体征待测" /> : null}{patient.alert_count ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}</Box><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>{patient.bedside_flags?.vs_trend || '暂无体征趋势'}{patient.bedside_flags?.fall_risk ? ` · 跌倒风险 ${patient.bedside_flags.fall_risk}` : ''}</Typography></Box><Typography variant="body2" color="text.secondary">BP {formatBp(vitals?.systolic, vitals?.diastolic)} · SpO2 {vitals?.spo2 ?? '--'}%</Typography><Box sx={{ display: 'flex', justifyContent: { xs: 'flex-start', lg: 'flex-end' }, gap: 0.5 }}><Button size="small" onClick={onOpen}>详情</Button>{onRecord ? <Button size="small" variant="outlined" onClick={onRecord}>录护理</Button> : null}</Box></Box>;
}

function asNursingPatient(patient: PatientDirectoryPatient, task?: NurseTask): NursePatientDetail {
  if (task) return { ...task, writable: true };
  return directoryPatientToNurseDetail(patient, '当前病区');
}

function toNurseTask(patient: NursePatientDetail): NurseTask {
  if (!patient.writable || patient.state_version == null) {
    console.warn('toNurseTask called on non-writable patient; returning safe mock task for display.', patient.patient_id);
    return { patient_id: patient.patient_id, state_version: 1, name: patient.name, disease: patient.disease, department: patient.department, risk_level: patient.risk_level, phase: patient.phase, round_count: patient.round_count, vital_signs_due: false, latest_vital_values: patient.latest_vital_values, alert_count: patient.alert_count, pending_nursing_actions: [], pending_medications: [], open_task_count: patient.open_task_count, task_items: patient.task_items, bedside_flags: patient.bedside_flags };
  }
  return { patient_id: patient.patient_id, state_version: patient.state_version, name: patient.name, disease: patient.disease, department: patient.department, risk_level: patient.risk_level, phase: patient.phase, round_count: patient.round_count, vital_signs_due: patient.vital_signs_due ?? false, latest_vital_values: patient.latest_vital_values, alert_count: patient.alert_count, pending_nursing_actions: [], pending_medications: [], open_task_count: patient.open_task_count, task_items: patient.task_items, bedside_flags: patient.bedside_flags };
}

function ColumnTitle({ children, align }: { children: React.ReactNode; align?: 'right' }) { return <Typography variant="caption" color="text.secondary" textAlign={align}>{children}</Typography>; }
