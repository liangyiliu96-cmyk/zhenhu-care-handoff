import { Alert, Box, Button, Card, Chip, CircularProgress, Typography } from '@mui/material';
import { FileText, RefreshCw, Route, Stethoscope } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { fetchWorkflowBriefs, generateWorkflowBrief } from '@/services/patient-service';
import type { WorkflowBrief } from '@/types/patient-dashboard';
import { CardSkeleton, ErrorBanner } from '@/components/shared/Feedback';

type WorkflowBriefKind = 'mdt' | 'follow_up' | 'transfer';

const BRIEFS: Array<{ kind: WorkflowBriefKind; label: string; icon: typeof Stethoscope; description: string }> = [
  { kind: 'mdt', label: 'MDT 会前简报', icon: Stethoscope, description: '归并风险、异常检验和待讨论问题。' },
  { kind: 'follow_up', label: '随访脚本', icon: FileText, description: '生成护士可修订的电话核对与异常升级问题。' },
  { kind: 'transfer', label: '转科交接', icon: Route, description: '整理转科原因、未完成事项与接收科关注点。' },
];

export default function WorkflowBriefsPanel({ patientId, stateVersion, generatableKinds = BRIEFS.map((item) => item.kind) }: { patientId: string; stateVersion: number; generatableKinds?: WorkflowBriefKind[] }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['patient', patientId, 'workflow-briefs'], queryFn: () => fetchWorkflowBriefs(patientId), staleTime: 30_000 });
  const [expectedVersion, setExpectedVersion] = useState(stateVersion);
  useEffect(() => setExpectedVersion(stateVersion), [stateVersion]);
  const mutation = useMutation({
    mutationFn: async (kind: WorkflowBriefKind) => {
      // Refresh immediately before a state-guarded write. The drawer prop and
      // cached list can both be stale after another clinical action completes.
      const latest = await query.refetch();
      const currentVersion = latest.data?.state_version ?? query.data?.state_version ?? expectedVersion;
      return generateWorkflowBrief(patientId, kind, currentVersion);
    },
    onSuccess: async (result) => {
      setExpectedVersion(result.state_version);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['patient', patientId] }),
        queryClient.invalidateQueries({ queryKey: ['nurse', 'patient', patientId] }),
      ]);
    },
  });
  if (query.isLoading) return <CardSkeleton height={210} />;
  if (query.error) return <ErrorBanner message="智能协同草稿加载失败" onRetry={() => void query.refetch()} />;
  const briefs = query.data?.briefs ?? {};
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}><FileText size={18} /><Typography variant="subtitle2" fontWeight={600}>智能协同草稿</Typography><Chip size="small" variant="outlined" label="需人工确认" sx={{ ml: 'auto' }} /></Box><Box sx={{ px: 1.75, pt: 1.2 }}><Alert severity="info">草稿不会自动创建会诊、转科、随访或外发消息，确认后请通过正式照护流程执行。</Alert></Box><Box sx={{ p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.25 }}>{BRIEFS.map((item, index) => <BriefRow key={item.kind} item={item} brief={briefs[item.kind]} canGenerate={generatableKinds.includes(item.kind)} pending={mutation.isPending} generating={mutation.variables} onGenerate={() => mutation.mutate(item.kind)} divider={index < BRIEFS.length - 1} />)}</Box>{mutation.error ? <Alert severity="error" sx={{ mx: 1.75, mb: 1.5 }}>{mutation.error instanceof Error ? mutation.error.message : '草稿生成失败'}</Alert> : null}</Card>;
}

function BriefRow({ item, brief, canGenerate, pending, generating, onGenerate, divider }: { item: typeof BRIEFS[number]; brief?: WorkflowBrief; canGenerate: boolean; pending: boolean; generating?: string; onGenerate: () => void; divider: boolean }) {
  const Icon = item.icon;
  return <Box sx={{ pb: divider ? 1.25 : 0, borderBottom: divider ? '1px solid' : 0, borderColor: 'divider' }}><Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}><Icon size={17} /><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" fontWeight={600}>{item.label}</Typography><Typography variant="caption" color="text.secondary">{item.description}</Typography></Box>{canGenerate ? <Button size="small" variant={brief ? 'text' : 'outlined'} aria-label={`${brief ? '更新' : '生成'}${item.label}`} disabled={pending} startIcon={pending && generating === item.kind ? <CircularProgress size={13} /> : <RefreshCw size={14} />} onClick={onGenerate}>{brief ? '更新' : '生成'}</Button> : null}</Box>{brief ? <Box sx={{ ml: 3.2, mt: 0.8, pl: 1, borderLeft: '2px solid', borderColor: brief.generation_source === 'llm_rag' ? 'info.main' : 'divider' }}><Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mb: 0.35 }}><Chip size="small" color={brief.generation_source === 'llm_rag' ? 'info' : 'default'} variant="outlined" label={brief.generation_source === 'llm_rag' ? 'LLM + RAG 草稿' : '规则草稿'} /><Typography variant="caption" color="text.secondary">引用 {brief.citations?.length ?? 0} 条</Typography></Box><Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{brief.content}</Typography></Box> : !canGenerate ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 3.2, mt: 0.5 }}>医生生成后可在这里查看。</Typography> : null}</Box>;
}
