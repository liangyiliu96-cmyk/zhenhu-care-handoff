import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, ListItemButton, Stack, TextField, Typography } from '@mui/material';
import { AlertTriangle, CheckCircle2, ClipboardCheck, Clock3, ListChecks, NotebookPen } from 'lucide-react';
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { CardSkeleton, EmptyState, ErrorBanner } from '@/components/shared/Feedback';
import { useChecklistExecution, useNursePriority, useNurseTasks, useNursingKpi, useShiftReport } from '@/hooks/use-nurse-management';
import { confirmChecklistRule } from '@/services/nurse-management-service';
import type { AdminTabId } from '@/core/admin-tabs';
import type { ChecklistExecutionRule, NurseTask, NursingTaskItem, NursingTaskType } from '@/types/nurse-management';

interface NurseManagementPanelProps {
  tab: Extract<AdminTabId, 'nursing' | 'handoff' | 'checklist'>;
  onOpenPatient?: (patientId: string) => void;
  onOpenTaskPatient?: (patient: NurseTask) => void;
  onRecordNursing?: (task: NurseTask) => void;
  onCompleteTask?: (patient: NurseTask, task: NursingTaskItem) => void;
  showKpi?: boolean;
}

export default function NurseManagementPanel({ tab, onOpenPatient, onOpenTaskPatient, onRecordNursing, onCompleteTask, showKpi = false }: NurseManagementPanelProps) {
  const queryClient = useQueryClient();
  const [confirmingRule, setConfirmingRule] = useState<ChecklistExecutionRule | null>(null);
  const [confirmationNote, setConfirmationNote] = useState('');
  const tasks = useNurseTasks(tab === 'nursing' || tab === 'checklist' || (tab === 'handoff' && Boolean(onOpenTaskPatient)));
  const priority = useNursePriority(tab === 'nursing');
  const kpi = useNursingKpi((tab === 'nursing' || tab === 'checklist') && showKpi);
  const handoff = useShiftReport(tab === 'handoff');
  const checklistExecution = useChecklistExecution(tab === 'checklist');
  const confirmationMutation = useMutation({
    mutationFn: () => confirmChecklistRule(confirmingRule!.rule_id, confirmationNote.trim()),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['nurse', 'checklist-execution'] }),
        queryClient.invalidateQueries({ queryKey: ['nurse', 'kpi'] }),
      ]);
      setConfirmingRule(null);
      setConfirmationNote('');
    },
  });

  if (tab === 'nursing') {
    if (tasks.isLoading || priority.isLoading || (showKpi && kpi.isLoading)) return <CardSkeleton height={240} />;
    if (tasks.error || priority.error || (showKpi && kpi.error)) return <ErrorBanner message="护理管理数据加载失败" onRetry={() => { void tasks.refetch(); void priority.refetch(); if (showKpi) void kpi.refetch(); }} />;
    const data = tasks.data;
    const visibleTasks = data?.tasks.filter((task) => (task.task_items?.length ?? 0) > 0 || task.alert_count > 0) ?? [];
    const hasPatientActions = Boolean(onOpenPatient || onOpenTaskPatient || onRecordNursing || onCompleteTask);
    return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Alert severity="info" icon={<ClipboardCheck size={18} />}>{priority.data?.advice ?? '暂无巡查优先级建议。'}</Alert>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: showKpi ? 'repeat(4, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}>
        <Metric label={showKpi ? '当前未完成' : '待关注患者'} value={showKpi ? kpi.data?.open_tasks ?? 0 : visibleTasks.length} icon={<ClipboardCheck size={18} />} />
        <Metric label={showKpi ? '24 小时完成' : '体征待测'} value={showKpi ? kpi.data?.completed_tasks ?? 0 : data?.vital_signs_overdue ?? 0} icon={<CheckCircle2 size={18} />} />
        <Metric label={showKpi ? '当前逾期' : '携带告警'} value={showKpi ? kpi.data?.overdue_tasks ?? 0 : data?.with_alerts ?? 0} icon={showKpi ? <Clock3 size={18} /> : <AlertTriangle size={18} />} />
        {showKpi ? <Metric label="执行完成率" value={`${Math.round((kpi.data?.completion_rate ?? 0) * 100)}%`} icon={<ClipboardCheck size={18} />} /> : null}
      </Box>
      {showKpi ? <NursingKpiDetail data={kpi.data} /> : null}
      {visibleTasks.length === 0 ? <EmptyState icon="" title="暂无护理任务" /> : <Card variant="outlined" sx={{ borderRadius: 1 }}>
        <Box sx={{ px: 2, py: 1, display: { xs: 'none', md: 'grid' }, gridTemplateColumns: hasPatientActions ? 'minmax(180px, 0.8fr) minmax(0, 1.6fr) 100px' : 'minmax(180px, 0.8fr) minmax(0, 1.6fr)', gap: 1, bgcolor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">患者</Typography><Typography variant="caption" color="text.secondary">待执行护理任务</Typography>{hasPatientActions ? <Typography variant="caption" color="text.secondary" textAlign="right">操作</Typography> : null}</Box>
        {visibleTasks.map((patient, index) => <NursingPatientTasks key={patient.patient_id} patient={patient} last={index === visibleTasks.length - 1} onOpenPatient={onOpenPatient} onOpenTaskPatient={onOpenTaskPatient} onRecordNursing={onRecordNursing} onCompleteTask={onCompleteTask} hasPatientActions={hasPatientActions} />)}
      </Card>}
    </Box>;
  }

  if (tab === 'handoff') {
    if (handoff.isLoading || (onOpenTaskPatient && tasks.isLoading)) return <CardSkeleton height={240} />;
    if (handoff.error || (onOpenTaskPatient && tasks.error)) return <ErrorBanner message="交班报告加载失败" onRetry={() => { void handoff.refetch(); void tasks.refetch(); }} />;
    const data = handoff.data;
    const tasksByPatientId = new Map((tasks.data?.tasks ?? []).map((task) => [task.patient_id, task]));
    return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}><Alert severity="info">{data?.ai_report ?? '暂无交班摘要。'}</Alert><Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}><Metric label="在院汇总" value={data?.total ?? 0} icon={<ClipboardCheck size={18} />} /><Metric label="重点关注" value={data?.high_focus.length ?? 0} icon={<AlertTriangle size={18} />} /><Metric label="今日出院" value={data?.today_discharge ?? 0} icon={<Clock3 size={18} />} /></Box>{!data ? <EmptyState icon="" title="暂无交班患者" /> : <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.35fr) minmax(300px, 0.65fr)' }, gap: 1.5, alignItems: 'start' }}><ShiftPatientGroup title="重点关注" patients={data.high_focus} tone="warning" onOpenPatient={onOpenPatient} onOpenTaskPatient={onOpenTaskPatient} tasksByPatientId={tasksByPatientId} /><Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}><ShiftPatientGroup title="今日出院" patients={data.discharge_today} tone="info" onOpenPatient={onOpenPatient} onOpenTaskPatient={onOpenTaskPatient} tasksByPatientId={tasksByPatientId} /><ShiftPatientGroup title="病情稳定" patients={data.stable} tone="default" onOpenPatient={onOpenPatient} onOpenTaskPatient={onOpenTaskPatient} tasksByPatientId={tasksByPatientId} /></Box></Box>}</Box>;
  }

  if (checklistExecution.isLoading || (showKpi && kpi.isLoading)) return <CardSkeleton height={320} />;
  if (checklistExecution.error || (showKpi && kpi.error)) return <ErrorBanner message="制度执行数据加载失败" onRetry={() => { void checklistExecution.refetch(); if (showKpi) void kpi.refetch(); }} />;
  const execution = checklistExecution.data;
  const rules = execution?.rules ?? [];
  const summary = execution?.summary ?? { total: 0, confirmed: 0, action_required: 0, not_triggered: 0, overdue: 0 };
  const hasPatientActions = Boolean(onOpenPatient || onOpenTaskPatient || onRecordNursing || onCompleteTask);
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <Alert severity={summary.action_required || summary.overdue ? 'warning' : 'success'} icon={<ListChecks size={18} />}>{summary.action_required ? `当前有 ${summary.action_required} 条制度项关联待执行患者任务。` : '当前没有制度项关联的待执行患者任务。'}</Alert>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(4, minmax(0, 1fr))' }, border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }}>
      <ExecutionStep step="1" label="制度标准" value={`${summary.total} 项`} />
      <ExecutionStep step="2" label="关联任务" value={`${summary.action_required} 项待处理`} tone={summary.action_required ? 'warning.main' : 'success.main'} />
      <ExecutionStep step="3" label="异常升级" value={`${summary.overdue} 项逾期`} tone={summary.overdue ? 'error.main' : 'success.main'} />
      <ExecutionStep step="4" label="确认留痕" value={`${summary.confirmed} 项已确认`} tone={summary.confirmed ? 'success.main' : 'text.secondary'} />
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: showKpi ? 'repeat(4, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))' }, gap: 1.5 }}>
      <Metric label="制度要求" value={summary.total} icon={<ListChecks size={18} />} />
      <Metric label="待闭环制度项" value={summary.action_required} icon={<ClipboardCheck size={18} />} />
      <Metric label="关联逾期" value={summary.overdue} icon={<Clock3 size={18} />} />
      {showKpi ? <Metric label="近 24 小时完成" value={kpi.data?.completed_tasks ?? 0} icon={<CheckCircle2 size={18} />} /> : null}
    </Box>
    {showKpi ? <NursingKpiDetail data={kpi.data} /> : null}
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.5, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><ListChecks size={18} /><Box><Typography variant="subtitle2" fontWeight={600}>{execution?.department || '当前科室'}制度执行</Typography><Typography variant="caption" color="text.secondary">展开制度项可查看关联患者任务；确认只用于无待办任务的班次制度核对。</Typography></Box></Box>
      {rules.length === 0 ? <EmptyState icon="" title="暂无制度执行标准" /> : rules.map((rule, index) => <ChecklistRuleRow key={rule.rule_id} rule={rule} last={index === rules.length - 1} canConfirm={Boolean(onRecordNursing || onCompleteTask)} onConfirm={() => { setConfirmationNote(''); setConfirmingRule(rule); }} onOpenPatient={onOpenPatient} onOpenTaskPatient={onOpenTaskPatient} onRecordNursing={onRecordNursing} onCompleteTask={onCompleteTask} hasPatientActions={hasPatientActions} />)}
    </Card>
    <ChecklistConfirmationDialog rule={confirmingRule} note={confirmationNote} pending={confirmationMutation.isPending} error={confirmationMutation.error} onChange={setConfirmationNote} onClose={() => { if (!confirmationMutation.isPending) setConfirmingRule(null); }} onConfirm={() => confirmationMutation.mutate()} />
  </Box>;
}

function ChecklistRuleRow({ rule, last, canConfirm, onConfirm, onOpenPatient, onOpenTaskPatient, onRecordNursing, onCompleteTask, hasPatientActions }: { rule: ChecklistExecutionRule; last: boolean; canConfirm: boolean; onConfirm: () => void; onOpenPatient?: (patientId: string) => void; onOpenTaskPatient?: (patient: NurseTask) => void; onRecordNursing?: (task: NurseTask) => void; onCompleteTask?: (patient: NurseTask, task: NursingTaskItem) => void; hasPatientActions: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const tone = rule.status === 'confirmed' ? 'success' : rule.status === 'action_required' ? 'warning' : 'default';
  const label = rule.status === 'confirmed' ? '已确认' : rule.status === 'action_required' ? '待闭环' : '无触发对象';
  return <Box sx={{ borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}>
    <Box sx={{ px: 1.5, py: 1.15, display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) auto auto' }, gap: 1, alignItems: 'center' }}>
      <Box sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', gap: 0.65, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{rule.title}</Typography><Chip size="small" color={tone} variant={rule.status === 'confirmed' ? 'filled' : 'outlined'} label={label} /></Box><Typography variant="caption" color="text.secondary">关联患者 {rule.patient_count} 人 · 关联任务 {rule.task_count} 项{rule.overdue_count ? ` · 逾期 ${rule.overdue_count} 项` : ''}</Typography>{rule.confirmation ? <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 0.25 }}>本窗口已由 {rule.confirmation.actor_name || rule.confirmation.actor_id || '护士'} 确认</Typography> : null}</Box>
      {rule.patient_count ? <Button size="small" variant="outlined" onClick={() => setExpanded((value) => !value)}>{expanded ? '收起患者' : '展开患者'}</Button> : null}
      {canConfirm && rule.status === 'not_triggered' ? <Button size="small" color="success" variant="outlined" onClick={onConfirm}>确认执行</Button> : null}
    </Box>
    {expanded ? <Box sx={{ px: 1.5, pb: 1.25, bgcolor: 'background.default' }}>{rule.patients.map((patient, index) => <Box key={patient.patient_id} sx={{ py: 1, borderTop: index ? '1px solid' : 0, borderColor: 'divider' }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Typography variant="caption" color="text.secondary">{patient.disease}</Typography>{patient.alert_count ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}<Box sx={{ ml: 'auto', display: 'flex', gap: 0.5 }}>{hasPatientActions && (onOpenTaskPatient || onOpenPatient) ? <Button size="small" onClick={() => onOpenTaskPatient ? onOpenTaskPatient(patient) : onOpenPatient?.(patient.patient_id)}>详情</Button> : null}{onRecordNursing ? <Button size="small" variant="outlined" startIcon={<NotebookPen size={14} />} onClick={() => onRecordNursing(patient)}>录护理</Button> : null}</Box></Box><Box sx={{ mt: 0.65, display: 'flex', flexDirection: 'column', gap: 0.45 }}>{patient.matched_tasks.map((task) => <Box key={task.task_key} sx={{ display: 'flex', gap: 0.75, alignItems: 'center' }}><Chip size="small" variant="outlined" label={nursingTaskLabel(task.task_type)} /><Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>{task.title}</Typography>{onCompleteTask ? <Button size="small" color="success" onClick={() => onCompleteTask(patient, task)}>完成</Button> : null}</Box>)}</Box></Box>)}</Box> : null}
  </Box>;
}

function ChecklistConfirmationDialog({ rule, note, pending, error, onChange, onClose, onConfirm }: { rule: ChecklistExecutionRule | null; note: string; pending: boolean; error: unknown; onChange: (value: string) => void; onClose: () => void; onConfirm: () => void }) {
  const errorText = error instanceof Error ? error.message : '';
  return <Dialog open={Boolean(rule)} onClose={pending ? undefined : onClose} fullWidth maxWidth="sm"><DialogTitle>确认本班制度执行</DialogTitle><DialogContent sx={{ pt: '12px !important' }}><Stack spacing={1.25}>{errorText ? <Alert severity="error">{errorText}</Alert> : null}<Typography variant="body2">{rule?.title}</Typography><Alert severity="info">该确认只记录本班制度核对留痕，不会代替患者任务、体征或护理记录。</Alert><TextField autoFocus label="确认备注" value={note} onChange={(event) => onChange(event.target.value)} multiline minRows={3} placeholder="记录核查范围、异常处理或交接说明" inputProps={{ maxLength: 500 }} /></Stack></DialogContent><DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" color="success" onClick={onConfirm} disabled={!note.trim() || pending}>确认并留痕</Button></DialogActions></Dialog>;
}

function NursingPatientTasks({ patient, last, onOpenPatient, onOpenTaskPatient, onRecordNursing, onCompleteTask, hasPatientActions }: { patient: NurseTask; last: boolean; onOpenPatient?: (patientId: string) => void; onOpenTaskPatient?: (patient: NurseTask) => void; onRecordNursing?: (task: NurseTask) => void; onCompleteTask?: (patient: NurseTask, task: NursingTaskItem) => void; hasPatientActions: boolean }) {
  const taskItems = patient.task_items ?? [];
  return <Box sx={{ px: 2, py: 1.4, display: { xs: 'flex', md: 'grid' }, flexDirection: 'column', gridTemplateColumns: hasPatientActions ? 'minmax(180px, 0.8fr) minmax(0, 1.6fr) 100px' : 'minmax(180px, 0.8fr) minmax(0, 1.6fr)', gap: { xs: 1, md: 1.5 }, alignItems: 'start', borderBottom: last ? 0 : '1px solid', borderColor: 'divider' }}>
    <Box sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{patient.name}</Typography>{patient.alert_count > 0 ? <Chip size="small" color="error" label={`${patient.alert_count} 告警`} /> : null}</Box><Typography variant="caption" color="text.secondary">{patient.disease} · {patient.department}</Typography></Box>
    {taskItems.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, width: '100%' }}>
      {taskItems.map((task) => <Box key={task.task_key} sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '110px minmax(0, 1fr) auto' }, gap: 1, alignItems: 'center', py: 0.65 }}>
        <Chip size="small" variant="outlined" color={task.priority === 'high' ? 'warning' : 'default'} label={nursingTaskLabel(task.task_type)} sx={{ justifySelf: 'start' }} />
        <Box sx={{ minWidth: 0 }}><Typography variant="body2">{task.title}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{task.description}</Typography></Box>
        {onCompleteTask ? <Button size="small" color="success" variant="text" startIcon={<CheckCircle2 size={15} />} onClick={() => onCompleteTask(patient, task)}>完成</Button> : null}
      </Box>)}
    </Box> : <Typography variant="caption" color="text.secondary">当前没有未完成任务。</Typography>}
    {hasPatientActions ? <Box sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' }, gap: 0.5 }}>{onOpenTaskPatient || onOpenPatient ? <Button size="small" onClick={() => onOpenTaskPatient ? onOpenTaskPatient(patient) : onOpenPatient?.(patient.patient_id)}>详情</Button> : null}{onRecordNursing ? <Button size="small" variant="outlined" startIcon={<NotebookPen size={15} />} onClick={() => onRecordNursing(patient)}>录护理</Button> : null}</Box> : null}
  </Box>;
}

function ShiftPatientGroup({ title, patients, tone, onOpenPatient, onOpenTaskPatient, tasksByPatientId }: { title: string; patients: Array<{ patient_id: string; name: string; news2?: number; alerts: number; shift_summary?: string }>; tone: 'warning' | 'info' | 'default'; onOpenPatient?: (patientId: string) => void; onOpenTaskPatient?: (patient: NurseTask) => void; tasksByPatientId?: Map<string, NurseTask> }) {
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.5, py: 1.05, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><Typography variant="subtitle2" fontWeight={600}>{title}</Typography><Chip size="small" color={tone === 'default' ? 'default' : tone} label={patients.length} sx={{ ml: 'auto' }} /></Box>{patients.length === 0 ? <Box sx={{ px: 1.5, py: 1.4 }}><Typography variant="body2" color="text.secondary">当前无患者。</Typography></Box> : patients.map((patient, index) => { const content = <><Typography variant="body2" fontWeight={600}>{patient.name}</Typography><Typography variant="caption" color="text.secondary">NEWS2 {patient.news2 ?? '未评分'} · 告警 {patient.alerts}{patient.shift_summary ? ` · ${patient.shift_summary}` : ''}</Typography></>; const task = tasksByPatientId?.get(patient.patient_id); return task && onOpenTaskPatient ? <ListItemButton key={patient.patient_id} onClick={() => onOpenTaskPatient(task)} sx={{ px: 1.5, py: 1.1, display: 'block', borderBottom: index === patients.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}>{content}</ListItemButton> : onOpenPatient ? <ListItemButton key={patient.patient_id} onClick={() => onOpenPatient(patient.patient_id)} sx={{ px: 1.5, py: 1.1, display: 'block', borderBottom: index === patients.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}>{content}</ListItemButton> : <Box key={patient.patient_id} sx={{ px: 1.5, py: 1.1, borderBottom: index === patients.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}>{content}</Box>; })}</Card>;
}

function NursingKpiDetail({ data }: { data: ReturnType<typeof useNursingKpi>['data'] }) {
  if (!data) return null;
  const types = (Object.entries(data.by_type) as Array<[NursingTaskType, { open: number; completed: number }]>).filter(([, value]) => value.open || value.completed);
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.5, py: 1.1, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><CheckCircle2 size={18} /><Typography variant="subtitle2" fontWeight={600}>护理执行质量 · 近 {data.window_hours} 小时</Typography><Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>{data.scope.departments.join('、') || '当前科室'}</Typography></Box>
    <Box sx={{ px: 1.5, py: 1.2, display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>{types.length ? types.map(([type, value]) => <Chip key={type} size="small" label={`${nursingTaskLabel(type)}：完成 ${value.completed} / 未完成 ${value.open}`} />) : <Typography variant="body2" color="text.secondary">当前没有可统计的护理任务。</Typography>}</Box>
    {data.recent_completions.length ? <><Divider /><Box sx={{ px: 1.5, py: 1 }}><Typography variant="caption" color="text.secondary">最近完成</Typography>{data.recent_completions.slice(0, 5).map((item) => <Box key={item.id} sx={{ display: 'flex', gap: 1, alignItems: 'baseline', py: 0.55 }}><Typography variant="body2" sx={{ minWidth: 90 }}>{item.patient_name}</Typography><Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>{item.title}</Typography><Typography variant="caption" color="text.secondary">{formatTime(item.completed_at)}</Typography></Box>)}</Box></> : null}
  </Card>;
}

function nursingTaskLabel(type: NursingTaskType) {
  return ({ vital_signs: '生命体征', nursing_action: '护理措施', medication: '用药核对', checklist: '制度执行' } as const)[type];
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function Metric({ label, value, icon }: { label: string; value: number | string; icon: React.ReactNode }) {
  return <Card variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}><Box sx={{ color: 'text.secondary', display: 'flex', gap: 0.75, alignItems: 'center' }}>{icon}<Typography variant="caption">{label}</Typography></Box><Typography variant="h5" sx={{ mt: 0.75 }}>{value}</Typography></Card>;
}

function ExecutionStep({ step, label, value, tone = 'primary.main' }: { step: string; label: string; value: string; tone?: string }) {
  return <Box sx={{ px: 1.25, py: 1.1, borderRight: { md: step === '4' ? 0 : '1px solid' }, borderBottom: { xs: Number(step) >= 3 ? 0 : '1px solid', md: 0 }, borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">第 {step} 步 · {label}</Typography><Typography variant="body2" fontWeight={700} color={tone} sx={{ mt: 0.3 }}>{value}</Typography></Box>;
}
