import { useEffect, useState } from 'react';
import { Alert, Box, Button, Card, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Stack, TextField, Typography } from '@mui/material';
import { Activity, ArrowRight, Bot, CheckCircle2, ClipboardCheck, FlaskConical, History, PencilLine, RefreshCw, ShieldCheck, Stethoscope } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { EmptyState, LoadingSkeleton } from '@/components/shared/Feedback';
import PreRoundBriefPanel, { type PreRoundBrief } from '@/components/clinical/PreRoundBriefPanel';
import { editPatientRound, generatePatientRound, generateProgressNoteDraft, reviewPatientRound } from '@/services/patient-service';
import type { ProgressNoteDraftResponse, RoundRecord, RoundsResponse } from '@/types/patient-dashboard';
import { clinicalPhaseLabel, formatRoundValue, latestRound, roundGenerationLabel, roundReviewLabel, roundSectionRows, type RoundSection } from '@/utils/round-display';

interface RoundsManagementPanelProps {
  patientId: string;
  stateVersion: number;
  loading: boolean;
  rounds?: RoundsResponse;
  preRoundBrief?: PreRoundBrief;
  preRoundBriefLoading?: boolean;
  preRoundBriefError?: string;
  onOpenMonitoring: () => void;
  onOpenOrders: () => void;
}

const SOAP_SECTIONS: Array<{ section: RoundSection; code: string; title: string; description: string; color: string }> = [
  { section: 'subjective', code: 'S', title: '主观情况', description: '患者主诉与查房间症状变化', color: 'info.main' },
  { section: 'objective', code: 'O', title: '客观数据', description: '体征、检验与风险数据摘要', color: 'success.main' },
  { section: 'assessment', code: 'A', title: '临床评估', description: '病情稳定性与治疗反应', color: 'warning.main' },
  { section: 'plan', code: 'P', title: '诊疗计划', description: '下一步监测、检查与处置方向', color: 'primary.main' },
];

export default function RoundsManagementPanel({ patientId, stateVersion, loading, rounds, preRoundBrief, preRoundBriefLoading, preRoundBriefError, onOpenMonitoring, onOpenOrders }: RoundsManagementPanelProps) {
  const queryClient = useQueryClient();
  const [editorOpen, setEditorOpen] = useState(false);
  const [copilotSeed, setCopilotSeed] = useState<Partial<RoundRevision> | undefined>();
  const refreshPatient = async () => {
    await queryClient.invalidateQueries({ queryKey: ['patient', patientId] });
  };
  const generateMutation = useMutation({ mutationFn: () => generatePatientRound(patientId, stateVersion), onSuccess: refreshPatient });
  const reviewMutation = useMutation({
    mutationFn: (roundNumber: number) => reviewPatientRound(patientId, roundNumber, { expected_version: stateVersion }),
    onSuccess: refreshPatient,
  });
  const editMutation = useMutation({
    mutationFn: (payload: RoundRevision) => editPatientRound(patientId, latestRound(rounds)?.round_number ?? rounds?.round_count ?? 1, { ...payload, expected_version: stateVersion }),
    onSuccess: async () => { await refreshPatient(); setEditorOpen(false); },
  });
  const progressDraftMutation = useMutation({ mutationFn: () => generateProgressNoteDraft(patientId, stateVersion) });
  if (loading) return <Card variant="outlined" sx={{ borderRadius: 1, p: 2 }}><LoadingSkeleton lines={10} height={18} /></Card>;
  const latest = latestRound(rounds);
  if (!latest) return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <PreRoundBriefPanel brief={preRoundBrief} loading={preRoundBriefLoading} generating={progressDraftMutation.isPending} error={preRoundBriefError || (progressDraftMutation.error instanceof Error ? progressDraftMutation.error.message : undefined)} onGenerateDraft={() => progressDraftMutation.mutate()} />
    {progressDraftMutation.data ? <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>先生成首次摘要</Button>}>已生成仅含来源事实的增量草稿。请先生成首次查房摘要，再在编辑器中补充并保存医生修订。</Alert> : null}
    <Card variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
      <EmptyState title="尚未生成查房摘要" description="可基于当前体征、检验、用药和病程数据生成第一轮结构化 SOAP 草稿。" />
      <Box sx={{ display: 'flex', justifyContent: 'center', pb: 2 }}>
        <Button variant="contained" startIcon={generateMutation.isPending ? <CircularProgress size={15} color="inherit" /> : <Bot size={16} />} disabled={generateMutation.isPending} onClick={() => generateMutation.mutate()}>{generateMutation.isPending ? '生成中...' : '生成首次查房摘要'}</Button>
      </Box>
      {generateMutation.error ? <Alert severity="error" sx={{ mt: 1.5 }}>{generateMutation.error instanceof Error ? generateMutation.error.message : '查房摘要生成失败'}</Alert> : null}
    </Card>
  </Box>;

  const history = [...(rounds?.rounds ?? [])].reverse();
  const actionError = generateMutation.error ?? reviewMutation.error;
  const applyProgressDraft = (draft: ProgressNoteDraftResponse) => {
    setCopilotSeed({
      subjective: draft.sections.subjective.status === 'draft' ? draft.sections.subjective.text : '',
      objective: draft.sections.objective.status === 'draft' ? draft.sections.objective.text : '',
    });
    setEditorOpen(true);
  };
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <PreRoundBriefPanel brief={preRoundBrief} loading={preRoundBriefLoading} generating={progressDraftMutation.isPending} error={preRoundBriefError || (progressDraftMutation.error instanceof Error ? progressDraftMutation.error.message : undefined)} onGenerateDraft={() => progressDraftMutation.mutate()} />
    {progressDraftMutation.data ? <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => applyProgressDraft(progressDraftMutation.data!)}>在编辑器中补充</Button>}>已生成仅含来源事实的增量草稿。评估与计划未被自动填写。</Alert> : null}
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 2, py: 1.6, display: 'flex', alignItems: 'flex-start', gap: 1.5, flexWrap: 'wrap', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ width: 36, height: 36, display: 'grid', placeItems: 'center', bgcolor: 'rgba(11, 100, 114, 0.09)', color: 'primary.dark', borderRadius: 1 }}><Stethoscope size={19} /></Box>
        <Box sx={{ flex: 1, minWidth: 240 }}><Typography variant="subtitle1">本轮查房摘要</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>由住院 Agent 汇总体征、检验、用药与病程数据生成，医生核对后再进入临床处置。</Typography></Box>
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}><Chip size="small" icon={<Bot size={14} />} label={roundGenerationLabel(latest)} color="info" variant="outlined" /><Chip size="small" icon={<ShieldCheck size={14} />} label={roundReviewLabel(latest)} color={latest.review_status === 'reviewed' ? 'success' : 'warning'} /></Box>
      </Box>

      <Box sx={{ px: 2, py: 1.25, display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) auto' }, gap: 1.5, alignItems: 'center', bgcolor: 'rgba(11, 100, 114, 0.035)', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box><Typography variant="caption" color="text.secondary">摘要生成路径</Typography><Typography variant="body2" sx={{ mt: 0.2 }}>住院 Agent `daily_round` 节点汇总病史、体征、检验、用药和既往病程，经过规则校验后由 LLM/RAG 增强为 SOAP 草稿。</Typography></Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button type="button" size="small" variant="outlined" startIcon={generateMutation.isPending ? <CircularProgress size={15} /> : <RefreshCw size={15} />} disabled={generateMutation.isPending || reviewMutation.isPending || editMutation.isPending} onClick={() => generateMutation.mutate()}>{generateMutation.isPending ? '生成中...' : '生成新一轮摘要'}</Button>
          <Button type="button" size="small" variant="outlined" startIcon={<PencilLine size={15} />} disabled={generateMutation.isPending || reviewMutation.isPending || editMutation.isPending} onClick={() => setEditorOpen(true)}>编辑本轮摘要</Button>
          <Button type="button" size="small" variant="contained" color="success" startIcon={reviewMutation.isPending ? <CircularProgress size={15} color="inherit" /> : <CheckCircle2 size={16} />} disabled={latest.review_status === 'reviewed' || reviewMutation.isPending || generateMutation.isPending || editMutation.isPending} onClick={() => reviewMutation.mutate(latest.round_number ?? rounds?.round_count ?? 1)}>{latest.review_status === 'reviewed' ? '医生已核对' : reviewMutation.isPending ? '记录中...' : '确认已核对'}</Button>
        </Box>
      </Box>

      {actionError || editMutation.error ? <Box sx={{ px: 2, pt: 1.5 }}><Alert severity="error">{actionError instanceof Error ? actionError.message : editMutation.error instanceof Error ? editMutation.error.message : '查房操作失败，请刷新后重试。'}</Alert></Box> : null}

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, borderBottom: '1px solid', borderColor: 'divider' }}>
        <RoundMetric label="查房轮次" value={`第 ${latest.round_number ?? rounds?.round_count ?? 1} 次`} />
        <RoundMetric label="生成时间" value={formatClinicalTime(latest.timestamp)} />
        <RoundMetric label="当前病程阶段" value={clinicalPhaseLabel(rounds?.phase)} last />
      </Box>

      <Box sx={{ p: 2, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' }, gap: 1.5 }}>
        {SOAP_SECTIONS.map((item) => <SoapSection key={item.section} record={latest} {...item} />)}
      </Box>

      {hasDoctorRevision(latest) ? <DoctorRevisionSummary record={latest} /> : null}

      <Divider />
      <Box sx={{ px: 2, py: 1.6, display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) auto' }, gap: 1.5, alignItems: 'center', bgcolor: 'rgba(237, 246, 247, 0.55)' }}>
        <Box><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}><Bot size={17} /><Typography variant="subtitle2">AI 临床行动建议</Typography></Box><Typography variant="body2" sx={{ mt: 0.55, lineHeight: 1.65 }}>{latest.ai_recommendation || '当前没有额外行动建议，请结合原始临床数据完成本轮核对。'}</Typography><Typography variant="caption" color="text.secondary">该建议不自动形成医嘱，也不会绕过医生审核。</Typography></Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}><Button type="button" size="small" variant="outlined" startIcon={<FlaskConical size={15} />} onClick={onOpenMonitoring}>查看原始监测</Button><Button type="button" size="small" variant="contained" endIcon={<ArrowRight size={15} />} onClick={onOpenOrders}>进入医嘱协同</Button></Box>
      </Box>

      {latest.citations?.length ? <Box sx={{ px: 2, py: 1.35, borderTop: '1px solid', borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">本轮建议关联 {latest.citations.length} 条临床证据引用，可在“临床证据与引用”中核查来源。</Typography></Box> : null}
    </Card>

    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 2, py: 1.35, display: 'flex', alignItems: 'center', gap: 0.8, borderBottom: '1px solid', borderColor: 'divider' }}><History size={18} /><Typography variant="subtitle2">历次查房记录</Typography><Chip size="small" variant="outlined" label={`${rounds?.total ?? history.length} 次`} sx={{ ml: 'auto' }} /></Box>
      <Box sx={{ px: 2 }}>
        {history.map((record, index) => <HistoryRow key={`${record.round_number ?? index}-${record.timestamp ?? index}`} record={record} latest={index === 0} onEdit={index === 0 ? () => setEditorOpen(true) : undefined} />)}
      </Box>
    </Card>
    <RoundEditDialog open={editorOpen} record={latest} seed={copilotSeed} pending={editMutation.isPending} onClose={() => { if (!editMutation.isPending) { setEditorOpen(false); setCopilotSeed(undefined); editMutation.reset(); } }} onSave={(revision) => editMutation.mutate(revision)} />
  </Box>;
}

export function LatestRoundSummary({ loading, rounds, onOpen }: { loading: boolean; rounds?: RoundsResponse; onOpen: () => void }) {
  const latest = latestRound(rounds);
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><Activity size={18} /><Typography variant="subtitle2">最近查房</Typography><Button size="small" endIcon={<ArrowRight size={14} />} onClick={onOpen} sx={{ ml: 'auto' }}>进入查房管理</Button></Box><Box sx={{ p: 1.75 }}>{loading ? <LoadingSkeleton lines={3} height={18} /> : !latest ? <EmptyState title="暂无查房记录" /> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.9 }}><Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}><Chip size="small" label={`第 ${latest.round_number ?? rounds?.round_count ?? 1} 次`} /><Chip size="small" variant="outlined" label={roundGenerationLabel(latest)} /><Chip size="small" color="warning" label={roundReviewLabel(latest)} /></Box><Typography variant="body2" sx={{ lineHeight: 1.65 }}>{latest.ai_recommendation || firstAssessment(latest) || '查房摘要已生成，请进入查房管理核对完整 SOAP。'}</Typography><Typography variant="caption" color="text.secondary">{formatClinicalTime(latest.timestamp)}</Typography></Box>}</Box></Card>;
}

function SoapSection({ record, section, code, title, description, color }: { record: RoundRecord; section: RoundSection; code: string; title: string; description: string; color: string }) {
  const rows = roundSectionRows(section, record[section]);
  return <Box sx={{ minHeight: 170, border: '1px solid', borderColor: 'divider', borderLeft: '4px solid', borderLeftColor: color, p: 1.5 }}><Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}><Box sx={{ width: 27, height: 27, display: 'grid', placeItems: 'center', borderRadius: 0.75, bgcolor: 'action.hover', fontWeight: 700, fontSize: 13 }}>{code}</Box><Box><Typography variant="subtitle2">{title}</Typography><Typography variant="caption" color="text.secondary">{description}</Typography></Box></Box><Box sx={{ mt: 1.2, display: 'flex', flexDirection: 'column', gap: 0.9 }}>{rows.length ? rows.map((row) => <Box key={row.key}><Typography variant="caption" color="text.secondary">{row.label}</Typography><Typography variant="body2" sx={{ mt: 0.1, lineHeight: 1.55 }}>{row.value}</Typography></Box>) : <Typography variant="body2" color="text.secondary">本节暂未记录。</Typography>}</Box></Box>;
}

function RoundMetric({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return <Box sx={{ px: 2, py: 1.2, borderRight: { md: last ? 0 : '1px solid' }, borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ mt: 0.2 }}>{value}</Typography></Box>;
}

function HistoryRow({ record, latest, onEdit }: { record: RoundRecord; latest: boolean; onEdit?: () => void }) {
  const assessment = firstAssessment(record);
  const revision = record.doctor_revision;
  return <Box sx={{ py: 1.35, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '110px minmax(0, 1fr) auto' }, gap: 1.25, alignItems: 'start', borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 0 } }}><Box><Typography variant="body2" fontWeight={600}>第 {record.round_number ?? '—'} 次查房</Typography><Typography variant="caption" color="text.secondary">{formatClinicalTime(record.timestamp)}</Typography></Box><Box><Typography variant="body2" sx={{ lineHeight: 1.6 }}>{assessment || record.ai_recommendation || '本轮查房已保存结构化记录。'}</Typography>{revision?.attention ? <Typography variant="caption" display="block" sx={{ mt: 0.45, color: 'primary.dark' }}>医生关注：{revision.attention}</Typography> : null}<Typography variant="caption" color="text.secondary">{roundGenerationLabel(record)}{record.edited_by ? ` · 医生已修订` : ''}</Typography></Box><Box sx={{ display: 'flex', alignItems: 'flex-end', flexDirection: 'column', gap: 0.5 }}><Chip size="small" icon={<ClipboardCheck size={14} />} color={record.review_status === 'reviewed' ? 'success' : 'warning'} variant={latest ? 'filled' : 'outlined'} label={latest ? '最新' : roundReviewLabel(record)} />{onEdit ? <Button size="small" variant="text" startIcon={<PencilLine size={14} />} onClick={onEdit}>编辑本轮</Button> : null}</Box></Box>;
}

type RoundRevision = { subjective: string; objective: string; assessment: string; plan: string; attention: string };

function RoundEditDialog({ open, record, seed, pending, onClose, onSave }: { open: boolean; record: RoundRecord; seed?: Partial<RoundRevision>; pending: boolean; onClose: () => void; onSave: (revision: RoundRevision) => void }) {
  const [draft, setDraft] = useState<RoundRevision>(() => initialRevision(record, seed));
  useEffect(() => { if (open) setDraft(initialRevision(record, seed)); }, [open, record, seed]);
  const setField = (field: keyof RoundRevision) => (event: React.ChangeEvent<HTMLInputElement>) => setDraft((current) => ({ ...current, [field]: event.target.value }));
  const canSave = Object.values(draft).some((value) => value.trim());
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="md"><DialogTitle>编辑第 {record.round_number ?? '—'} 次查房摘要</DialogTitle><DialogContent sx={{ pt: '12px !important' }}><Alert severity="info" sx={{ mb: 1.5 }}>保存后会形成独立的医生修订版，保留原始 Agent 摘要与生成证据。</Alert><Stack spacing={1.5}><TextField autoFocus label="主观情况修订" value={draft.subjective} onChange={setField('subjective')} multiline minRows={2} /><TextField label="客观数据修订" value={draft.objective} onChange={setField('objective')} multiline minRows={2} /><TextField label="临床评估修订" value={draft.assessment} onChange={setField('assessment')} multiline minRows={3} /><TextField label="诊疗计划修订" value={draft.plan} onChange={setField('plan')} multiline minRows={3} /><TextField label="本轮医生关注点" value={draft.attention} onChange={setField('attention')} multiline minRows={2} placeholder="例如：关注低钾风险、晨间复查肾功能后再评估利尿方案" /></Stack></DialogContent><DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" onClick={() => onSave(draft)} disabled={!canSave || pending} startIcon={pending ? <CircularProgress size={14} color="inherit" /> : <PencilLine size={15} />}>{pending ? '保存中...' : '保存医生修订'}</Button></DialogActions></Dialog>;
}

function initialRevision(record: RoundRecord, seed?: Partial<RoundRevision>): RoundRevision {
  const revision = record.doctor_revision;
  return {
    subjective: revision?.subjective || formatRoundValue(record.subjective),
    objective: revision?.objective || formatRoundValue(record.objective),
    assessment: revision?.assessment || formatRoundValue(record.assessment),
    plan: revision?.plan || formatRoundValue(record.plan),
    attention: revision?.attention || '',
    ...seed,
  };
}

function hasDoctorRevision(record: RoundRecord) {
  return Object.values(record.doctor_revision ?? {}).some((value) => Boolean(value?.trim()));
}

function DoctorRevisionSummary({ record }: { record: RoundRecord }) {
  const revision = record.doctor_revision ?? {};
  const items = [['医生临床评估', revision.assessment], ['医生诊疗计划', revision.plan], ['本轮关注点', revision.attention]].filter(([, value]) => Boolean(value?.trim()));
  return <Box sx={{ mx: 2, mb: 2, px: 1.5, py: 1.35, border: '1px solid', borderColor: 'primary.light', bgcolor: 'rgba(11, 100, 114, 0.035)' }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}><PencilLine size={16} /><Typography variant="subtitle2">医生修订版</Typography><Typography variant="caption" color="text.secondary">{record.edited_by ? `由 ${record.edited_by} 于 ${formatClinicalTime(record.edited_at)} 保存` : ''}</Typography></Box><Stack spacing={0.75} sx={{ mt: 1 }}>{items.map(([label, value]) => <Box key={label}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ lineHeight: 1.6 }}>{value}</Typography></Box>)}</Stack></Box>;
}

function firstAssessment(record: RoundRecord) {
  return roundSectionRows('assessment', record.assessment).find((row) => row.key === 'response_to_treatment')?.value
    ?? roundSectionRows('assessment', record.assessment)[0]?.value;
}

function formatClinicalTime(value?: string) {
  if (!value) return '时间未记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
