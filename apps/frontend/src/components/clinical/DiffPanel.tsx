import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  MenuItem,
  TextField,
  Typography,
} from '@mui/material';
import { BookOpen, Check, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { submitReview } from '@/services/review-service';
import type { PendingItem, PendingPatient, ReviewDecision, ReviewSubmission } from '@/types/ward';
import EvidencePanel from './EvidencePanel';

interface DiffPanelProps {
  patient: PendingPatient | null;
  item: PendingItem | null;
  onClose: () => void;
  onRefresh: () => Promise<unknown>;
}

interface HandoffDraft {
  type: string;
  content: string;
  originalIndex?: number;
}

const reviewTitles = {
  doctor_confirm: '入院诊断审核',
  med_confirm: '用药调整审核',
  discharge_sign: '出院签字审核',
} as const;

export default function DiffPanel({ patient, item, onClose, onRefresh }: DiffPanelProps) {
  const queryClient = useQueryClient();
  const payload = item?.payload ?? {};
  const [comment, setComment] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [showEvidence, setShowEvidence] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [chiefComplaint, setChiefComplaint] = useState('');
  const [hpi, setHpi] = useState('');
  const [pe, setPe] = useState('');
  const [ddxDraft, setDdxDraft] = useState<Array<Record<string, unknown>>>([]);
  const [newDiagnosis, setNewDiagnosis] = useState('');
  const [medAction, setMedAction] = useState<'continue' | 'adjust' | 'new_labs' | 'discharge'>('continue');
  const [medication, setMedication] = useState('');
  const [dose, setDose] = useState('');
  const [frequency, setFrequency] = useState('');
  const [labOrders, setLabOrders] = useState('');
  const [handoffDraft, setHandoffDraft] = useState<HandoffDraft[]>([]);

  useEffect(() => {
    const nextPayload = item?.payload ?? {};
    setComment('');
    setRejectionReason('');
    setShowEvidence(false);
    setConflict(false);
    setErrorMessage('');
    setChiefComplaint(text(nextPayload.chief_complaint));
    setHpi(text(nextPayload.hpi_narrative));
    setPe(text(nextPayload.pe_narrative));
    setDdxDraft([...(nextPayload.ddx_list ?? [])]);
    setNewDiagnosis('');
    setMedAction('continue');
    setMedication('');
    setDose('');
    setFrequency('');
    setLabOrders('');
    setHandoffDraft((nextPayload.handoff_items ?? []).map((entry, index) => ({
      type: text(entry.type) || 'instruction', content: text(entry.content), originalIndex: index,
    })));
  }, [item]);

  const mutation = useMutation({
    mutationFn: (decision: ReviewDecision) => {
      if (!patient || !item) throw new Error('审核项目不存在');
      const submission = buildSubmission({
        patient, item, decision, comment, rejectionReason,
        chiefComplaint, hpi, pe, ddxDraft,
        medAction, medication, dose, frequency, labOrders,
        handoffDraft,
      });
      return submitReview(patient.patient_id, submission);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['ward', 'pending'] }),
        queryClient.invalidateQueries({ queryKey: ['ward', 'alerts'] }),
        queryClient.invalidateQueries({ queryKey: ['ward', 'patients'] }),
        patient ? queryClient.invalidateQueries({ queryKey: ['patient', patient.patient_id] }) : Promise.resolve(),
        patient ? queryClient.invalidateQueries({ queryKey: ['evidence', patient.patient_id] }) : Promise.resolve(),
      ]);
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiClientError && error.code === 'STATE_VERSION_CONFLICT') {
        setConflict(true);
        return;
      }
      setErrorMessage(error instanceof Error ? error.message : '提交审核失败，请稍后重试。');
    },
  });

  const handleRefresh = async () => {
    setErrorMessage('');
    await onRefresh();
    setConflict(false);
  };

  const validationError = useMemo(() => approvalValidation(item, { medAction, medication, labOrders, handoffDraft }), [item, medAction, medication, labOrders, handoffDraft]);
  const rejectDisabled = rejectionReason.trim().length < 10 || mutation.isPending || conflict;
  const approveDisabled = Boolean(validationError) || mutation.isPending || conflict;
  const title = item ? reviewTitles[item.review_type] : '审核';

  return (
    <Drawer anchor="right" open={Boolean(patient && item)} onClose={mutation.isPending ? undefined : onClose}>
      <Box sx={{ width: { xs: '100vw', sm: 640 }, maxWidth: '100vw', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Box sx={{ p: 2, display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
            {patient ? <Typography variant="body2" color="text.secondary">{patient.name} · {patient.disease} · 状态 v{patient.state_version}</Typography> : null}
          </Box>
          <IconButton aria-label="关闭审核面板" onClick={onClose} disabled={mutation.isPending}><X size={18} /></IconButton>
        </Box>
        <Divider />

        <Box sx={{ p: 2, overflow: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {conflict ? <Alert severity="warning" action={<Button color="inherit" size="small" startIcon={<RefreshCw size={14} />} onClick={handleRefresh}>刷新</Button>}>该患者已由其他临床人员更新。当前草稿会保留，请刷新后重新核对。</Alert> : null}
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          {validationError ? <Alert severity="warning">{validationError}</Alert> : null}

          <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Box><Typography variant="overline" color="text.secondary">审核项目</Typography><Typography variant="body2">{item?.label}</Typography></Box>
            <Typography variant="caption" color="text.secondary" fontFamily="var(--font-mono)">{item?.review_id || '未提供审核编号'}</Typography>
          </Box>

          {item?.review_type === 'doctor_confirm' ? <AdmissionReviewEditor payload={payload} chiefComplaint={chiefComplaint} hpi={hpi} pe={pe} ddx={ddxDraft} newDiagnosis={newDiagnosis} disabled={mutation.isPending || conflict} onChiefComplaint={setChiefComplaint} onHpi={setHpi} onPe={setPe} onNewDiagnosis={setNewDiagnosis} onDdx={setDdxDraft} /> : null}
          {item?.review_type === 'med_confirm' ? <MedicationReviewEditor payload={payload} action={medAction} medication={medication} dose={dose} frequency={frequency} labs={labOrders} disabled={mutation.isPending || conflict} onAction={setMedAction} onMedication={setMedication} onDose={setDose} onFrequency={setFrequency} onLabs={setLabOrders} /> : null}
          {item?.review_type === 'discharge_sign' ? <DischargeReviewEditor payload={payload} items={handoffDraft} disabled={mutation.isPending || conflict} onItems={setHandoffDraft} /> : null}

          <Button variant="outlined" color="inherit" size="small" startIcon={<BookOpen size={16} />} onClick={() => setShowEvidence((value) => !value)} sx={{ alignSelf: 'flex-start' }}>
            {showEvidence ? '收起证据链' : '查看证据链'}
          </Button>
          {patient ? <EvidencePanel patientId={patient.patient_id} enabled={showEvidence} /> : null}

          <TextField label="审核备注" value={comment} onChange={(event) => setComment(event.target.value)} multiline minRows={2} fullWidth disabled={mutation.isPending || conflict} />
          <TextField label="拒绝原因（拒绝时必填，至少 10 字）" value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} multiline minRows={2} fullWidth disabled={mutation.isPending || conflict} />
        </Box>

        <Divider />
        <Box sx={{ p: 2, display: 'flex', gap: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <Button color="error" variant="outlined" onClick={() => mutation.mutate('rejected')} disabled={rejectDisabled}>拒绝</Button>
          <Button variant="contained" onClick={() => mutation.mutate(item?.review_type === 'discharge_sign' ? 'signed' : 'approved')} disabled={approveDisabled} startIcon={mutation.isPending ? <CircularProgress size={14} color="inherit" /> : <Check size={16} />}>
            {item?.review_type === 'discharge_sign' ? '签字并提交交接' : '批准并继续流程'}
          </Button>
        </Box>
      </Box>
    </Drawer>
  );
}

function AdmissionReviewEditor({ payload, chiefComplaint, hpi, pe, ddx, newDiagnosis, disabled, onChiefComplaint, onHpi, onPe, onNewDiagnosis, onDdx }: { payload: Record<string, unknown>; chiefComplaint: string; hpi: string; pe: string; ddx: Array<Record<string, unknown>>; newDiagnosis: string; disabled: boolean; onChiefComplaint: (value: string) => void; onHpi: (value: string) => void; onPe: (value: string) => void; onNewDiagnosis: (value: string) => void; onDdx: (value: Array<Record<string, unknown>>) => void }) {
  const addDiagnosis = () => {
    const diagnosis = newDiagnosis.trim();
    if (!diagnosis || ddx.some((entry) => text(entry.diagnosis) === diagnosis)) return;
    onDdx([...ddx, { diagnosis, likelihood: 'moderate', source: 'doctor' }]);
    onNewDiagnosis('');
  };
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
    <SectionHeading title="临床草稿" detail="核对并编辑主诉、现病史、查体及鉴别诊断" />
    <TextField label="主诉" value={chiefComplaint} onChange={(event) => onChiefComplaint(event.target.value)} disabled={disabled} />
    <TextField label="现病史" value={hpi} onChange={(event) => onHpi(event.target.value)} multiline minRows={3} disabled={disabled} />
    <TextField label="体格检查" value={pe} onChange={(event) => onPe(event.target.value)} multiline minRows={3} disabled={disabled} />
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      <Typography variant="caption" color="text.secondary">鉴别诊断</Typography>
      {ddx.length ? ddx.map((entry, index) => <Box key={`${text(entry.diagnosis)}-${index}`} sx={{ display: 'flex', gap: 1, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider', pb: 0.75 }}><Box sx={{ flex: 1 }}><Typography variant="body2" fontWeight={600}>{text(entry.diagnosis) || '未命名诊断'}</Typography><Typography variant="caption" color="text.secondary">可能性 {text(entry.likelihood) || '未分级'}{entry.key_findings ? ` · ${display(entry.key_findings)}` : ''}</Typography></Box><IconButton aria-label="移除鉴别诊断" size="small" disabled={disabled} onClick={() => onDdx(ddx.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></IconButton></Box>) : <Typography variant="body2" color="text.secondary">当前没有可审核的鉴别诊断。</Typography>}
      <Box sx={{ display: 'flex', gap: 0.75 }}><TextField size="small" label="新增诊断" value={newDiagnosis} onChange={(event) => onNewDiagnosis(event.target.value)} disabled={disabled} fullWidth /><IconButton aria-label="新增鉴别诊断" disabled={disabled || !newDiagnosis.trim()} onClick={addDiagnosis}><Plus size={18} /></IconButton></Box>
    </Box>
    <ContextList label="临床告警" values={payload.clinical_alerts} />
  </Box>;
}

function MedicationReviewEditor({ payload, action, medication, dose, frequency, labs, disabled, onAction, onMedication, onDose, onFrequency, onLabs }: { payload: Record<string, unknown>; action: 'continue' | 'adjust' | 'new_labs' | 'discharge'; medication: string; dose: string; frequency: string; labs: string; disabled: boolean; onAction: (value: 'continue' | 'adjust' | 'new_labs' | 'discharge') => void; onMedication: (value: string) => void; onDose: (value: string) => void; onFrequency: (value: string) => void; onLabs: (value: string) => void }) {
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
    <SectionHeading title="调药建议" detail="结合异常体征、检验和现有方案做出结构化决策" />
    <ContextList label="AI 调药建议" values={payload.medication_adjustments} />
    <ContextList label="近期用药告警" values={payload.recent_alerts} />
    <ContextList label="异常检验" values={payload.abnormal_labs} />
    <TextField select label="医生决策" value={action} onChange={(event) => onAction(event.target.value as typeof action)} disabled={disabled}>
      <MenuItem value="continue">维持当前方案</MenuItem><MenuItem value="adjust">调整或新增用药</MenuItem><MenuItem value="new_labs">追加检验</MenuItem><MenuItem value="discharge">转入出院评估</MenuItem>
    </TextField>
    {action === 'adjust' ? <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1.2fr 0.8fr 0.8fr' }, gap: 1 }}><TextField label="药物" value={medication} onChange={(event) => onMedication(event.target.value)} disabled={disabled} /><TextField label="剂量" value={dose} onChange={(event) => onDose(event.target.value)} disabled={disabled} /><TextField label="频次" value={frequency} onChange={(event) => onFrequency(event.target.value)} disabled={disabled} /></Box> : null}
    {action === 'new_labs' ? <TextField label="追加检验项目" helperText="多个项目使用逗号或分号分隔" value={labs} onChange={(event) => onLabs(event.target.value)} disabled={disabled} /> : null}
    {action === 'discharge' ? <Alert severity="warning">批准后将设置出院决定并进入出院签字链，请先核对出院条件。</Alert> : null}
  </Box>;
}

function DischargeReviewEditor({ payload, items, disabled, onItems }: { payload: Record<string, unknown>; items: HandoffDraft[]; disabled: boolean; onItems: (value: HandoffDraft[]) => void }) {
  const update = (index: number, content: string) => onItems(items.map((entry, itemIndex) => itemIndex === index ? { ...entry, content } : entry));
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
    <SectionHeading title="出院与交接" detail="签字前逐项核对交接内容，修改会写回主流程" />
    <ContextList label="出院标准" values={payload.discharge_criteria_check} />
    <ContextList label="并发症与风险" values={payload.complication_risks} />
    <ContextList label="当前用药" values={payload.medication_current} />
    <Typography variant="caption" color="text.secondary">交接事项</Typography>
    {items.map((entry, index) => <Box key={`${entry.originalIndex ?? 'new'}-${index}`} sx={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 36px', gap: 0.75, alignItems: 'start' }}><Chip size="small" label={entry.type || 'instruction'} variant="outlined" sx={{ mt: 1 }} /><TextField value={entry.content} onChange={(event) => update(index, event.target.value)} multiline minRows={2} disabled={disabled} /><IconButton aria-label="移除交接事项" size="small" sx={{ mt: 0.75 }} disabled={disabled} onClick={() => onItems(items.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></IconButton></Box>)}
    <Button variant="outlined" size="small" startIcon={<Plus size={16} />} disabled={disabled} onClick={() => onItems([...items, { type: 'instruction', content: '' }])} sx={{ alignSelf: 'flex-start' }}>增加交接事项</Button>
  </Box>;
}

function SectionHeading({ title, detail }: { title: string; detail: string }) { return <Box><Typography variant="subtitle2" fontWeight={600}>{title}</Typography><Typography variant="caption" color="text.secondary">{detail}</Typography></Box>; }

function ContextList({ label, values }: { label: string; values: unknown }) {
  const entries = Array.isArray(values) ? values : values && typeof values === 'object' ? [values] : [];
  if (!entries.length) return null;
  return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Box sx={{ mt: 0.5, display: 'flex', flexDirection: 'column', gap: 0.5 }}>{entries.slice(0, 8).map((entry, index) => <Typography key={index} variant="body2" sx={{ borderLeft: '2px solid', borderColor: 'divider', pl: 1, lineHeight: 1.55 }}>{display(entry)}</Typography>)}</Box></Box>;
}

function buildSubmission(values: { patient: PendingPatient; item: PendingItem; decision: ReviewDecision; comment: string; rejectionReason: string; chiefComplaint: string; hpi: string; pe: string; ddxDraft: Array<Record<string, unknown>>; medAction: 'continue' | 'adjust' | 'new_labs' | 'discharge'; medication: string; dose: string; frequency: string; labOrders: string; handoffDraft: HandoffDraft[] }): ReviewSubmission {
  const submission: ReviewSubmission = {
    review_type: values.item.review_type,
    decision: values.decision,
    comment: values.comment.trim(),
    reject_reason: values.decision === 'rejected' ? values.rejectionReason.trim() : undefined,
    expected_version: values.patient.state_version,
  };
  if (values.decision === 'rejected') return submission;
  if (values.item.review_type === 'doctor_confirm') {
    submission.edits = {
      chief_complaint: values.chiefComplaint.trim(), hpi_narrative: values.hpi.trim(), pe_narrative: values.pe.trim(),
      ddx_edits: buildDdxEdits(values.item.payload?.ddx_list ?? [], values.ddxDraft),
    };
  }
  if (values.item.review_type === 'med_confirm') {
    submission.doctor_action = values.medAction;
    if (values.medAction === 'adjust') submission.doctor_orders = { medication: values.medication.trim(), dose: values.dose.trim(), frequency: values.frequency.trim() };
    if (values.medAction === 'new_labs') submission.doctor_orders = { labs: splitItems(values.labOrders).map((name) => ({ name })) };
  }
  if (values.item.review_type === 'discharge_sign') {
    submission.handoff_edits = buildHandoffEdits(values.item.payload?.handoff_items ?? [], values.handoffDraft);
  }
  return submission;
}

function buildDdxEdits(original: Array<Record<string, unknown>>, current: Array<Record<string, unknown>>) {
  const originalNames = original.map((entry) => text(entry.diagnosis)).filter(Boolean);
  const currentNames = current.map((entry) => text(entry.diagnosis)).filter(Boolean);
  return [
    ...originalNames.filter((name) => !currentNames.includes(name)).map((diagnosis) => ({ action: 'remove' as const, diagnosis })),
    ...current.filter((entry) => !originalNames.includes(text(entry.diagnosis))).map((item) => ({ action: 'add' as const, item })),
    { action: 'reorder' as const, new_order: currentNames },
  ];
}

function buildHandoffEdits(original: Array<Record<string, unknown>>, current: HandoffDraft[]) {
  const retained = new Set(current.flatMap((entry) => entry.originalIndex == null ? [] : [entry.originalIndex]));
  const removals = original.map((_, index) => index).filter((index) => !retained.has(index)).sort((a, b) => b - a).map((index) => ({ action: 'remove' as const, index }));
  const edits: NonNullable<ReviewSubmission['handoff_edits']> = [];
  current.forEach((entry) => {
    if (entry.originalIndex == null) {
      edits.push({ action: 'add', item: { type: entry.type, content: entry.content.trim() } });
      return;
    }
    const source = original[entry.originalIndex] ?? {};
    if (text(source.type) === entry.type && text(source.content) === entry.content) return;
    edits.push({ action: 'edit', index: entry.originalIndex, item: { type: entry.type, content: entry.content.trim() } });
  });
  return [...edits, ...removals];
}

function approvalValidation(item: PendingItem | null, values: { medAction: string; medication: string; labOrders: string; handoffDraft: HandoffDraft[] }) {
  if (!item) return '';
  if (item.review_type === 'med_confirm' && values.medAction === 'adjust' && !values.medication.trim()) return '调整用药时必须填写药物名称。';
  if (item.review_type === 'med_confirm' && values.medAction === 'new_labs' && splitItems(values.labOrders).length === 0) return '追加检验时至少填写一个检验项目。';
  if (item.review_type === 'discharge_sign' && (!values.handoffDraft.length || values.handoffDraft.some((entry) => !entry.content.trim()))) return '出院签字前必须保留至少一条完整交接事项。';
  return '';
}

function splitItems(value: string) { return value.split(/[，,；;]/).map((entry) => entry.trim()).filter(Boolean); }
function text(value: unknown) { return typeof value === 'string' || typeof value === 'number' ? String(value) : ''; }
function display(value: unknown) { if (typeof value === 'string' || typeof value === 'number') return String(value); try { return JSON.stringify(value, null, 0); } catch { return '无法显示'; } }
