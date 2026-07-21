import { useEffect, useState } from 'react';
import { Alert, Box, Button, Card, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Tab, Tabs, TextField, Typography } from '@mui/material';
import { BookOpenCheck, Siren } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { fetchEducationResources, type EducationResource } from '@/services/education-service';
import { acknowledgeEducation, fetchPatientDashboard } from '@/services/patient-service';
import { educationQuery, type EducationMode } from '@/utils/education-utils';

interface DischargeEducationPanelProps {
  patientId: string;
  stateVersion: number;
  disease: string;
  diseaseId?: string;
  openRecordRequest?: number;
}

export default function DischargeEducationPanel({ patientId, stateVersion, disease, diseaseId = '', openRecordRequest = 0 }: DischargeEducationPanelProps) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<EducationMode>('guidance');
  const [recording, setRecording] = useState<EducationResource | null>(null);
  const [recipient, setRecipient] = useState<'patient' | 'family' | 'caregiver'>('patient');
  const [teachBack, setTeachBack] = useState('');
  const [error, setError] = useState('');
  const resources = useQuery({
    queryKey: ['education-resources', disease, diseaseId, mode],
    queryFn: () => fetchEducationResources(educationQuery(disease, mode), diseaseId),
    staleTime: 60_000,
    retry: false,
  });
  const matchingResources = (resources.data?.results ?? []).filter((resource) => matchesEducationResource(resource, disease, diseaseId));
  const mutation = useMutation({
    mutationFn: async () => {
      let expectedVersion = stateVersion;
      try {
        const latest = await fetchPatientDashboard(patientId);
        expectedVersion = latest.state_version;
      } catch {
        // Preserve the current concurrency guard if a preflight refresh is unavailable.
      }
      return acknowledgeEducation(patientId, {
        topic: resourceTitle(recording), recipient, teach_back: teachBack.trim(), expected_version: expectedVersion,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['patient', patientId] });
      setRecording(null);
      setRecipient('patient');
      setTeachBack('');
      setError('');
    },
    onError: (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
        setError('患者状态已更新，请刷新出院资料后重新确认宣教记录。');
        void queryClient.invalidateQueries({ queryKey: ['patient', patientId] });
        return;
      }
      setError(cause instanceof Error ? cause.message : '宣教记录提交失败，请稍后重试。');
    },
  });

  useEffect(() => {
    if (!openRecordRequest || mutation.isPending) return;
    setRecording({ topic: `${disease || '出院'}患者教育与回授` });
    setError('');
  }, [disease, mutation.isPending, openRecordRequest]);

  const closeRecording = () => { if (!mutation.isPending) { setRecording(null); setTeachBack(''); setError(''); } };
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, pt: 1.25, display: 'flex', alignItems: 'center', gap: 0.75 }}><BookOpenCheck size={18} /><Typography variant="subtitle2" fontWeight={600}>出院患者教育</Typography></Box>
    <Tabs value={mode} onChange={(_, value: EducationMode) => setMode(value)} sx={{ px: 1 }}><Tab value="guidance" icon={<BookOpenCheck size={15} />} iconPosition="start" label="出院指导" /><Tab value="emergency" icon={<Siren size={15} />} iconPosition="start" label="急诊识别" /></Tabs>
    <Box sx={{ px: 1.75, pb: 1.75 }}>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.25 }}>以下为 L9 知识库资料，用于宣教浏览，不作为患者级临床结论。</Typography>
      {resources.isLoading ? <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={22} /></Box> : null}
      {resources.error ? <Alert severity="warning">患者教育资料暂时无法加载，请在资料恢复后完成宣教。</Alert> : null}
      {!resources.isLoading && !resources.error && matchingResources.length === 0 ? <Typography variant="body2" color="text.secondary">暂无匹配当前病种的知识库资料；请依据已完成的面对面宣教记录真实回授。</Typography> : null}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>{matchingResources.map((resource, index) => <EducationResourceCard key={`${resource.topic ?? 'resource'}-${index}`} resource={resource} onRecord={() => { setRecording(resource); setError(''); }} />)}</Box>
      <Box sx={{ mt: 1.25, pt: 1.25, borderTop: '1px solid', borderColor: 'divider' }}>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>宣教已在床旁、电话或门诊完成时，可直接记录患者或照护者的回授。</Typography>
        <Button size="small" variant="outlined" onClick={() => { setRecording({ topic: `${disease || '出院'}患者教育与回授` }); setError(''); }}>记录本次宣教与回授</Button>
      </Box>
    </Box>
    <Dialog open={recording !== null} onClose={closeRecording} fullWidth maxWidth="xs"><DialogTitle>记录已完成的宣教</DialogTitle><DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>{error ? <Alert severity="error">{error}</Alert> : null}<TextField label="宣教主题" value={resourceTitle(recording)} disabled /><TextField select label="接受者" value={recipient} onChange={(event) => setRecipient(event.target.value as 'patient' | 'family' | 'caregiver')}><MenuItem value="patient">患者</MenuItem><MenuItem value="family">家属</MenuItem><MenuItem value="caregiver">照护者</MenuItem></TextField><TextField label="回授摘要" value={teachBack} onChange={(event) => setTeachBack(event.target.value)} multiline minRows={2} placeholder="记录患者或家属复述的要点" /></DialogContent><DialogActions><Button onClick={closeRecording} disabled={mutation.isPending}>取消</Button><Button variant="contained" onClick={() => mutation.mutate()} disabled={mutation.isPending} startIcon={mutation.isPending ? <CircularProgress size={15} color="inherit" /> : undefined}>确认记录</Button></DialogActions></Dialog>
  </Card>;
}

function EducationResourceCard({ resource, onRecord }: { resource: EducationResource; onRecord: () => void }) {
  return <Box sx={{ borderLeft: '3px solid', borderColor: 'success.main', pl: 1.25 }}><Typography variant="body2" fontWeight={600}>{resourceTitle(resource)}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.45, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{String(resource.text || '未提供资料内容')}</Typography><Box sx={{ mt: 0.75, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}><Typography variant="caption" color="text.secondary">来源：{String(resource.source || 'L9 知识库')}</Typography><Button size="small" variant="text" onClick={onRecord}>记录已宣教</Button></Box></Box>;
}

function resourceTitle(resource: EducationResource | null): string {
  return String(resource?.topic || '出院患者教育');
}

function matchesEducationResource(resource: EducationResource, disease: string, diseaseId: string): boolean {
  if (diseaseId && resource.disease_id) return resource.disease_id === diseaseId;
  const subject = disease.trim();
  if (!subject) return true;
  const searchable = [resource.topic, resource.text].filter(Boolean).join(' ');
  return searchable.includes(subject);
}
