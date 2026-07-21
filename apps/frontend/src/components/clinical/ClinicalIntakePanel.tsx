import { useState } from 'react';
import { ClipboardPenLine, Stethoscope } from 'lucide-react';
import { Alert, Box, Button, Card, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { recordHistory, recordPhysicalExam } from '@/services/patient-service';

export default function ClinicalIntakePanel({ patientId, stateVersion }: { patientId: string; stateVersion: number }) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'history' | 'physical' | null>(null);
  const [chiefComplaint, setChiefComplaint] = useState('');
  const [hpi, setHpi] = useState('');
  const [general, setGeneral] = useState('');
  const [chestLungs, setChestLungs] = useState('');
  const [chestHeart, setChestHeart] = useState('');
  const mutation = useMutation({ mutationFn: () => mode === 'history' ? recordHistory(patientId, { chief_complaint: chiefComplaint.trim(), hpi_narrative: hpi.trim() || undefined, expected_version: stateVersion }) : recordPhysicalExam(patientId, { general: general.trim() || undefined, chest_lungs: chestLungs.trim() || undefined, chest_heart: chestHeart.trim() || undefined, expected_version: stateVersion }), onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['patient', patientId] }), queryClient.invalidateQueries({ queryKey: ['ward'] })]); close(); } });
  const close = () => { if (!mutation.isPending) { setMode(null); mutation.reset(); } };
  const error = mutation.error instanceof ApiClientError && mutation.error.code === 'STATE_VERSION_CONFLICT' ? '患者状态已更新，请刷新页面后重新核对并提交。' : mutation.error instanceof Error ? mutation.error.message : '';
  const canSubmit = mode === 'history' ? Boolean(chiefComplaint.trim()) : Boolean(general.trim() || chestLungs.trim() || chestHeart.trim());
  return <Card variant="outlined" sx={{ borderRadius: 1 }}><Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><ClipboardPenLine size={18} /><Typography variant="subtitle2" fontWeight={600}>入院采集</Typography></Box><Box sx={{ p: 1.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}><Button size="small" variant="outlined" startIcon={<ClipboardPenLine size={16} />} onClick={() => setMode('history')}>录入病史</Button><Button size="small" variant="outlined" startIcon={<Stethoscope size={16} />} onClick={() => setMode('physical')}>录入体格检查</Button></Box><Dialog open={mode !== null} onClose={close} fullWidth maxWidth="sm"><DialogTitle>{mode === 'history' ? '录入病史' : '录入体格检查'}</DialogTitle><DialogContent sx={{ pt: '12px !important' }}><Stack spacing={1.5}>{error ? <Alert severity="warning">{error}</Alert> : null}{mode === 'history' ? <><TextField autoFocus label="主诉" value={chiefComplaint} onChange={(event) => setChiefComplaint(event.target.value)} required multiline minRows={2} /><TextField label="现病史" value={hpi} onChange={(event) => setHpi(event.target.value)} multiline minRows={4} /></> : <><TextField autoFocus label="一般情况" value={general} onChange={(event) => setGeneral(event.target.value)} multiline minRows={2} /><TextField label="胸肺检查" value={chestLungs} onChange={(event) => setChestLungs(event.target.value)} multiline minRows={2} /><TextField label="心脏检查" value={chestHeart} onChange={(event) => setChestHeart(event.target.value)} multiline minRows={2} /></>}</Stack></DialogContent><DialogActions><Button onClick={close} disabled={mutation.isPending}>取消</Button><Button variant="contained" disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>提交记录</Button></DialogActions></Dialog></Card>;
}
