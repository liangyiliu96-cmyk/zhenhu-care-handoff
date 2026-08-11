import { useEffect, useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { recordNursing } from '@/services/patient-service';
import type { NurseTask } from '@/types/nurse-management';

export default function NursingEntryDialog({ task, onClose }: { task: NurseTask | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [actions, setActions] = useState('');
  const [intake, setIntake] = useState('');
  const [output, setOutput] = useState('');
  const [spo2, setSpo2] = useState('');
  const [heartRate, setHeartRate] = useState('');
  const [alerts, setAlerts] = useState('');
  useEffect(() => {
    setActions('');
    setIntake('');
    setOutput('');
    setSpo2('');
    setHeartRate('');
    setAlerts('');
  }, [task?.patient_id, task?.state_version]);
  const mutation = useMutation({ mutationFn: () => recordNursing(task!.patient_id, { vital_signs: { ...(spo2 ? { spo2: Number(spo2) } : {}), ...(heartRate ? { heart_rate: Number(heartRate) } : {}) }, intake_ml: Number(intake || 0), output_ml: Number(output || 0), nursing_actions: actions.trim(), alerts: alerts.split(/[；;,，]/).map((item) => item.trim()).filter(Boolean), expected_version: task!.state_version }), onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['nurse'] }), queryClient.invalidateQueries({ queryKey: ['ward'] }), queryClient.invalidateQueries({ queryKey: ['patient', task!.patient_id] }), queryClient.invalidateQueries({ queryKey: ['nurse', 'patient', task!.patient_id, 'records'] })]); onClose(); } });
  const error = mutation.error instanceof ApiClientError && mutation.error.code === 'STATE_VERSION_CONFLICT' ? '患者状态已更新，请刷新任务后重新记录。' : mutation.error instanceof Error ? mutation.error.message : '';
  return <Dialog open={Boolean(task)} onClose={mutation.isPending ? undefined : onClose} fullWidth maxWidth="sm"><DialogTitle>护理记录{task ? ` · ${task.name}` : ''}</DialogTitle><DialogContent sx={{ pt: '12px !important' }}><Stack spacing={1.5}>{error ? <Alert severity="warning">{error}</Alert> : null}<TextField autoFocus label="护理措施" value={actions} onChange={(event) => setActions(event.target.value)} multiline minRows={3} required placeholder="记录已执行的护理措施" /><Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}><TextField label="入量 (ml)" type="number" value={intake} onChange={(event) => setIntake(event.target.value)} fullWidth /><TextField label="出量 (ml)" type="number" value={output} onChange={(event) => setOutput(event.target.value)} fullWidth /></Stack><Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}><TextField label="SpO2 (%)" type="number" value={spo2} onChange={(event) => setSpo2(event.target.value)} fullWidth /><TextField label="心率 (次/分)" type="number" value={heartRate} onChange={(event) => setHeartRate(event.target.value)} fullWidth /></Stack><TextField label="异常上报" value={alerts} onChange={(event) => setAlerts(event.target.value)} multiline minRows={2} placeholder="多项以逗号或分号分隔" /></Stack></DialogContent><DialogActions><Button onClick={onClose} disabled={mutation.isPending}>取消</Button><Button variant="contained" onClick={() => mutation.mutate()} disabled={!actions.trim() || mutation.isPending}>提交记录</Button></DialogActions></Dialog>;
}
