import { useState, type ChangeEvent, type Dispatch, type SetStateAction } from 'react';
import { Alert, Box, Button, Card, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider, MenuItem, TextField, Typography } from '@mui/material';
import { ClipboardCheck, ClipboardPlus, HeartHandshake } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { acknowledgeEducation, createFollowUpTask, createInvestigationOrder, createMedicationOrder, createMdtRequest, fetchCareManagement, resolveMdtRequest, updateFollowUpTask, updateInvestigationOrder, updateMedicationOrder } from '@/services/patient-service';
import type { CareManagementResponse } from '@/types/patient-dashboard';
import { canSubmitCareAction, careActionLabel, type CareAction } from '@/utils/care-utils';
import { investigationTransitions, lifecycleStatusLabel, mdtDecisionLabel, medicationTransitions, type FollowUpStatus, type InvestigationTransitionStatus, type MdtDecision, type MedicationOrderStatus, type MedicationTransitionStatus } from '@/utils/care-lifecycle-utils';
import { CardSkeleton, EmptyState } from '@/components/shared/Feedback';

interface CareManagementPanelProps { patientId: string; stateVersion: number; defaultOpen?: boolean; }
type Fields = Record<string, string>;
type CareRecords = CareManagementResponse['care_management'];
type RecordItem = Record<string, unknown>;
type LifecycleDialog =
  | { kind: 'medication'; recordId: string; recordLabel: string; status: MedicationTransitionStatus }
  | { kind: 'investigation'; recordId: string; recordLabel: string; status: InvestigationTransitionStatus }
  | { kind: 'mdt'; recordId: string; recordLabel: string }
  | { kind: 'followup'; recordId: string; recordLabel: string; status: FollowUpStatus };

const blankFields: Fields = {
  medication: '', dose: '', frequency: '', route: 'PO', indication: '', testName: '', priority: 'routine', reason: '', timing: '', instructions: '', specialties: '', topic: '', recipient: 'patient', teachBack: '', title: '', dueAt: '', assignee: '', transitionNote: '', mdtDecision: 'accepted', mdtSummary: '',
};

export default function CareManagementPanel({ patientId, stateVersion, defaultOpen = false }: CareManagementPanelProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(defaultOpen);
  const [action, setAction] = useState<CareAction | null>(null);
  const [transition, setTransition] = useState<LifecycleDialog | null>(null);
  const [fields, setFields] = useState<Fields>(blankFields);
  const [error, setError] = useState('');
  const [transitionError, setTransitionError] = useState('');
  const care = useQuery({ queryKey: ['patient', patientId, 'care-management'], queryFn: () => fetchCareManagement(patientId), enabled: open, staleTime: 30_000 });

  const refreshRelated = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['patient', patientId] }),
      queryClient.invalidateQueries({ queryKey: ['ward'] }),
    ]);
  };

  const reportError = (cause: unknown, setMessage: (message: string) => void) => {
    if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
      setMessage('患者状态已更新。已刷新当前数据，请核对最新状态后再次确认操作。');
      void refreshRelated();
      return;
    }
    setMessage(cause instanceof Error ? cause.message : '照护操作提交失败。');
  };

  const createMutation = useMutation({
    mutationFn: async (next: CareAction) => {
      if (next === 'medication') return createMedicationOrder(patientId, { medication: fields.medication.trim(), dose: fields.dose.trim(), frequency: fields.frequency.trim(), route: fields.route.trim() || 'PO', indication: fields.indication.trim(), expected_version: stateVersion });
      if (next === 'investigation') return createInvestigationOrder(patientId, { test_name: fields.testName.trim(), priority: fields.priority as 'routine' | 'urgent', reason: fields.reason.trim(), timing: fields.timing.trim(), instructions: fields.instructions.trim(), expected_version: stateVersion });
      if (next === 'mdt') return createMdtRequest(patientId, { reason: fields.reason.trim(), specialties: fields.specialties.split(',').map((item) => item.trim()).filter(Boolean), expected_version: stateVersion });
      if (next === 'education') return acknowledgeEducation(patientId, { topic: fields.topic.trim(), recipient: fields.recipient as 'patient' | 'family' | 'caregiver', teach_back: fields.teachBack.trim(), expected_version: stateVersion });
      return createFollowUpTask(patientId, { title: fields.title.trim(), due_at: fields.dueAt, assignee: fields.assignee.trim() || undefined, expected_version: stateVersion });
    },
    onSuccess: async () => {
      await refreshRelated();
      setAction(null);
      setFields(blankFields);
    },
    onError: (cause) => reportError(cause, setError),
  });

  const lifecycleMutation = useMutation({
    mutationFn: async (next: LifecycleDialog) => {
      if (next.kind === 'medication') return updateMedicationOrder(patientId, next.recordId, { status: next.status, note: fields.transitionNote.trim(), expected_version: stateVersion });
      if (next.kind === 'investigation') return updateInvestigationOrder(patientId, next.recordId, { status: next.status, note: fields.transitionNote.trim(), expected_version: stateVersion });
      if (next.kind === 'mdt') return resolveMdtRequest(patientId, next.recordId, { decision: fields.mdtDecision as MdtDecision, summary: fields.mdtSummary.trim(), expected_version: stateVersion });
      return updateFollowUpTask(patientId, next.recordId, { status: next.status, note: fields.transitionNote.trim(), expected_version: stateVersion });
    },
    onSuccess: async () => {
      await refreshRelated();
      setTransition(null);
      setFields(blankFields);
    },
    onError: (cause) => reportError(cause, setTransitionError),
  });

  const start = (next: CareAction) => { setAction(next); setFields(blankFields); setError(''); };
  const startTransition = (next: LifecycleDialog) => { setTransition(next); setFields(blankFields); setTransitionError(''); };
  const closeCreate = () => { if (!createMutation.isPending) { setAction(null); setError(''); } };
  const closeTransition = () => { if (!lifecycleMutation.isPending) { setTransition(null); setTransitionError(''); } };
  const records = care.data?.care_management;

  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: open ? '1px solid' : 0, borderColor: 'divider' }}><HeartHandshake size={18} /><Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>照护管理</Typography><Button size="small" variant="text" onClick={() => setOpen((value) => !value)} sx={{ textTransform: 'none' }}>{open ? '收起' : '展开'}</Button></Box>
    {open ? <Box sx={{ p: 1.75 }}>
      <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 1.5 }}><Button size="small" variant="outlined" startIcon={<ClipboardPlus size={15} />} onClick={() => start('medication')} sx={{ textTransform: 'none' }}>新增医嘱</Button><Button size="small" variant="outlined" startIcon={<ClipboardPlus size={15} />} onClick={() => start('investigation')} sx={{ textTransform: 'none' }}>开立检查</Button><Button size="small" variant="outlined" onClick={() => start('mdt')} sx={{ textTransform: 'none' }}>发起 MDT</Button><Button size="small" variant="outlined" onClick={() => start('education')} sx={{ textTransform: 'none' }}>记录宣教</Button><Button size="small" variant="outlined" onClick={() => start('followup')} sx={{ textTransform: 'none' }}>创建随访</Button></Box>
      {care.isLoading ? <CardSkeleton height={100} /> : care.error ? <Alert severity="warning">照护记录暂时无法加载。</Alert> : !records ? <EmptyState icon="" title="暂无照护记录" /> : <CareRecordsView records={records} onTransition={startTransition} />}
    </Box> : null}
    <CreateDialog action={action} fields={fields} error={error} pending={createMutation.isPending} onChange={setFields} onClose={closeCreate} onSubmit={() => action && createMutation.mutate(action)} />
    <LifecycleDialog transition={transition} fields={fields} error={transitionError} pending={lifecycleMutation.isPending} onChange={setFields} onClose={closeTransition} onSubmit={() => transition && lifecycleMutation.mutate(transition)} />
  </Card>;
}

function CareRecordsView({ records, onTransition }: { records: CareRecords; onTransition: (transition: LifecycleDialog) => void }) {
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
    <CareRecordSection label="医嘱" items={records.medication_orders} onTransition={onTransition} />
    <Divider />
    <CareRecordSection label="检查" items={records.investigation_orders ?? []} onTransition={onTransition} />
    <Divider />
    <CareRecordSection label="MDT" items={records.mdt_requests} onTransition={onTransition} />
    <Divider />
    <CareRecordSection label="宣教计划" items={records.education_plans ?? []} onTransition={onTransition} />
    <Divider />
    <CareRecordSection label="宣教" items={records.education_records} onTransition={onTransition} />
    <Divider />
    <CareRecordSection label="随访" items={records.follow_up_tasks} onTransition={onTransition} />
  </Box>;
}

function CareRecordSection({ label, items, onTransition }: { label: string; items: RecordItem[]; onTransition: (transition: LifecycleDialog) => void }) {
  return <Box><Typography variant="caption" color="text.secondary">{label} · {items.length} 条</Typography>{items.length === 0 ? <Typography variant="body2" color="text.secondary" sx={{ mt: 0.35 }}>暂无记录</Typography> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 0.75 }}>{items.slice(-5).reverse().map((record, index) => <CareRecordRow key={String(record.id ?? index)} category={label} record={record} onTransition={onTransition} />)}</Box>}</Box>;
}

function CareRecordRow({ category, record, onTransition }: { category: string; record: RecordItem; onTransition: (transition: LifecycleDialog) => void }) {
  const id = text(record.id);
  const label = recordLabel(record);
  const status = text(record.status);
  return <Box sx={{ borderLeft: '3px solid', borderColor: 'info.main', pl: 1.25 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{label}</Typography>{status ? <Chip size="small" label={lifecycleStatusLabel(status)} variant="outlined" /> : null}</Box>
    <Typography variant="caption" color="text.secondary" display="block">{recordContext(category, record)}</Typography>
    {id ? <TransitionActions category={category} recordId={id} recordLabel={label} status={status} onTransition={onTransition} /> : null}
  </Box>;
}

function TransitionActions({ category, recordId, recordLabel, status, onTransition }: { category: string; recordId: string; recordLabel: string; status: string; onTransition: (transition: LifecycleDialog) => void }) {
  if (category === '医嘱') {
    const actions = medicationTransitions(status);
    return actions.length ? <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 0.75 }}>{actions.map((action) => <Button key={action.status} size="small" variant="text" onClick={() => onTransition({ kind: 'medication', recordId, recordLabel, status: action.status })} sx={{ textTransform: 'none' }}>{action.label}</Button>)}</Box> : null;
  }
  if (category === '检查') {
    const actions = investigationTransitions(status);
    return actions.length ? <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 0.75 }}>{actions.map((action) => <Button key={action.status} size="small" variant="text" color={action.status === 'cancelled' ? 'error' : 'primary'} onClick={() => onTransition({ kind: 'investigation', recordId, recordLabel, status: action.status })} sx={{ textTransform: 'none' }}>{action.label}</Button>)}</Box> : null;
  }
  if (category === 'MDT' && status === 'requested') return <Button size="small" variant="text" onClick={() => onTransition({ kind: 'mdt', recordId, recordLabel })} sx={{ mt: 0.75, textTransform: 'none' }}>处理 MDT</Button>;
  if (category === '随访' && status === 'pending') return <Box sx={{ display: 'flex', gap: 0.75, mt: 0.75 }}><Button size="small" variant="text" startIcon={<ClipboardCheck size={14} />} onClick={() => onTransition({ kind: 'followup', recordId, recordLabel, status: 'completed' })} sx={{ textTransform: 'none' }}>完成</Button><Button size="small" variant="text" color="error" onClick={() => onTransition({ kind: 'followup', recordId, recordLabel, status: 'cancelled' })} sx={{ textTransform: 'none' }}>取消</Button></Box>;
  return null;
}

function CreateDialog({ action, fields, error, pending, onChange, onClose, onSubmit }: { action: CareAction | null; fields: Fields; error: string; pending: boolean; onChange: Dispatch<SetStateAction<Fields>>; onClose: () => void; onSubmit: () => void }) {
  return <Dialog open={action !== null} onClose={onClose} fullWidth maxWidth="xs"><DialogTitle>{action ? careActionLabel(action) : '照护操作'}</DialogTitle><DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>{error ? <Alert severity="error">{error}</Alert> : null}{action === 'medication' ? <><TextField label="药品名称" value={fields.medication} onChange={change('medication', onChange)} required /><TextField label="剂量" value={fields.dose} onChange={change('dose', onChange)} required /><TextField label="频次" value={fields.frequency} onChange={change('frequency', onChange)} required /><TextField label="给药途径" value={fields.route} onChange={change('route', onChange)} /><TextField label="适应证" value={fields.indication} onChange={change('indication', onChange)} /></> : null}{action === 'investigation' ? <><TextField label="检查或检验项目" value={fields.testName} onChange={change('testName', onChange)} required /><TextField select label="优先级" value={fields.priority} onChange={change('priority', onChange)}><MenuItem value="routine">常规</MenuItem><MenuItem value="urgent">紧急</MenuItem></TextField><TextField label="检查原因" value={fields.reason} onChange={change('reason', onChange)} multiline minRows={2} required /><TextField label="计划时间" value={fields.timing} onChange={change('timing', onChange)} /><TextField label="执行注意事项" value={fields.instructions} onChange={change('instructions', onChange)} multiline minRows={2} /></> : null}{action === 'mdt' ? <><TextField label="会诊原因" value={fields.reason} onChange={change('reason', onChange)} multiline minRows={3} required /><TextField label="会诊专科（逗号分隔）" value={fields.specialties} onChange={change('specialties', onChange)} required /></> : null}{action === 'education' ? <><TextField label="宣教主题" value={fields.topic} onChange={change('topic', onChange)} required /><TextField select label="接受者" value={fields.recipient} onChange={change('recipient', onChange)}><MenuItem value="patient">患者</MenuItem><MenuItem value="family">家属</MenuItem><MenuItem value="caregiver">照护者</MenuItem></TextField><TextField label="回授摘要" value={fields.teachBack} onChange={change('teachBack', onChange)} multiline minRows={2} /></> : null}{action === 'followup' ? <><TextField label="随访事项" value={fields.title} onChange={change('title', onChange)} required /><TextField label="计划时间" type="datetime-local" value={fields.dueAt} onChange={change('dueAt', onChange)} InputLabelProps={{ shrink: true }} required /><TextField label="负责人" value={fields.assignee} onChange={change('assignee', onChange)} /></> : null}</DialogContent><DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" onClick={onSubmit} disabled={!action || !canSubmitCareAction(action, fields) || pending} startIcon={pending ? <CircularProgress size={14} color="inherit" /> : undefined}>{action ? careActionLabel(action) : '提交'}</Button></DialogActions></Dialog>;
}

function LifecycleDialog({ transition, fields, error, pending, onChange, onClose, onSubmit }: { transition: LifecycleDialog | null; fields: Fields; error: string; pending: boolean; onChange: Dispatch<SetStateAction<Fields>>; onClose: () => void; onSubmit: () => void }) {
  const isMdt = transition?.kind === 'mdt';
  const label = transition ? transitionLabel(transition) : '更新照护记录';
  const noteValue = isMdt ? fields.mdtSummary : fields.transitionNote;
  const isDestructive = (
    (transition?.kind === 'medication' || transition?.kind === 'investigation') && transition.status === 'cancelled'
  ) || (transition?.kind === 'medication' && transition.status === 'discontinued');
  return <Dialog open={transition !== null} onClose={onClose} fullWidth maxWidth="xs"><DialogTitle>{label}</DialogTitle><DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>{error ? <Alert severity="error">{error}</Alert> : null}<Typography variant="body2" color="text.secondary">{transition?.recordLabel}</Typography>{isMdt ? <><TextField select label="MDT 结论" value={fields.mdtDecision} onChange={change('mdtDecision', onChange)}>{(['accepted', 'deferred', 'declined'] as MdtDecision[]).map((decision) => <MenuItem key={decision} value={decision}>{mdtDecisionLabel(decision)}</MenuItem>)}</TextField><TextField label="结论摘要" value={fields.mdtSummary} onChange={change('mdtSummary', onChange)} multiline minRows={3} required /></> : <TextField label="操作说明" value={fields.transitionNote} onChange={change('transitionNote', onChange)} multiline minRows={3} required />}</DialogContent><DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" color={isDestructive ? 'error' : 'primary'} onClick={onSubmit} disabled={!transition || !noteValue.trim() || pending} startIcon={pending ? <CircularProgress size={14} color="inherit" /> : undefined}>确认{label}</Button></DialogActions></Dialog>;
}

function transitionLabel(transition: LifecycleDialog): string {
  if (transition.kind === 'mdt') return '处理 MDT 请求';
  if (transition.kind === 'followup') return transition.status === 'completed' ? '完成随访任务' : '取消随访任务';
  if (transition.kind === 'investigation') return ({ scheduled: '安排检查', completed: '完成检查', cancelled: '取消检查' } as Record<InvestigationTransitionStatus, string>)[transition.status];
  return ({ active: '激活医嘱', held: '暂停医嘱', discontinued: '停用医嘱', cancelled: '取消医嘱' } as Partial<Record<MedicationOrderStatus, string>>)[transition.status] || '更新医嘱';
}

function change(key: string, setFields: Dispatch<SetStateAction<Fields>>) { return (event: ChangeEvent<HTMLInputElement>) => setFields((current) => ({ ...current, [key]: event.target.value })); }
function text(value: unknown): string { return typeof value === 'string' || typeof value === 'number' ? String(value) : ''; }
function recordLabel(record: RecordItem) { return text(record.medication) || text(record.test_name) || text(record.reason) || text(record.topic) || text(record.title) || text(record.id) || '未命名记录'; }
function recordContext(category: string, record: RecordItem) {
  if (category === '医嘱') return [text(record.dose), text(record.frequency), text(record.route), text(record.indication), text(record.status_note)].filter(Boolean).join(' · ') || '未提供医嘱详情';
  if (category === '检查') return [text(record.priority) === 'urgent' ? '紧急' : '常规', text(record.reason), text(record.timing), text(record.instructions), text(record.status_note)].filter(Boolean).join(' · ') || '未提供检查详情';
  if (category === 'MDT') return [Array.isArray(record.specialties) ? record.specialties.map(text).filter(Boolean).join('、') : '', text(record.summary)].filter(Boolean).join(' · ') || '未提供会诊详情';
  if (category === '随访') return [text(record.due_at), text(record.assignee), text(record.note)].filter(Boolean).join(' · ') || '未提供随访详情';
  if (category === '宣教计划') return [text(record.recipient), Array.isArray(record.key_points) ? record.key_points.map(text).filter(Boolean).join('、') : ''].filter(Boolean).join(' · ') || '待执行宣教计划';
  return [text(record.recipient), text(record.teach_back)].filter(Boolean).join(' · ') || '已记录宣教';
}
