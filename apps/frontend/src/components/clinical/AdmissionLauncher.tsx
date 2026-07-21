import { useState } from 'react';
import { CirclePlus } from 'lucide-react';
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { createAdmission } from '@/services/patient-service';

export default function AdmissionLauncher({ onCreated }: { onCreated: (patientId: string) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [patientId, setPatientId] = useState('');
  const [diseaseId, setDiseaseId] = useState('');
  const mutation = useMutation({ mutationFn: () => createAdmission(patientId.trim(), diseaseId.trim()), onSuccess: async (data) => { await queryClient.invalidateQueries({ queryKey: ['ward'] }); setOpen(false); onCreated(data.patient_id); } });
  const close = () => { if (!mutation.isPending) { setOpen(false); setPatientId(''); setDiseaseId(''); mutation.reset(); } };
  return <><Button variant="contained" size="small" startIcon={<CirclePlus size={16} />} onClick={() => setOpen(true)}>新建入院</Button><Dialog open={open} onClose={close} fullWidth maxWidth="xs"><DialogTitle>新建入院</DialogTitle><DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>{mutation.error ? <Alert severity="error">{mutation.error instanceof Error ? mutation.error.message : '创建入院失败'}</Alert> : null}<TextField autoFocus label="患者编号" value={patientId} onChange={(event) => setPatientId(event.target.value)} required disabled={mutation.isPending} helperText="使用院内唯一患者编号" /><TextField label="病种模板 ID" value={diseaseId} onChange={(event) => setDiseaseId(event.target.value)} required disabled={mutation.isPending} helperText="例如 hypertension、heart_failure" /></DialogContent><DialogActions><Button onClick={close} disabled={mutation.isPending}>取消</Button><Button variant="contained" disabled={!patientId.trim() || !diseaseId.trim() || mutation.isPending} onClick={() => mutation.mutate()} startIcon={mutation.isPending ? <CircularProgress size={15} color="inherit" /> : undefined}>创建并进入</Button></DialogActions></Dialog></>;
}
