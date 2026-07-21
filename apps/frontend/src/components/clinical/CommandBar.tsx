import { useState } from 'react';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import { ClipboardCheck, Pause, Play, Stethoscope, Workflow } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { submitDoctorCommand } from '@/services/patient-service';
import { commandLabel, commandNeedsTarget, commandRequiresReason, type DoctorCommandAction } from '@/utils/command-utils';

interface CommandBarProps {
  patientId: string;
  stateVersion: number;
  isOnHold: boolean;
  canStartDischarge: boolean;
  onOpenDischarge: () => void;
}

export default function CommandBar({ patientId, stateVersion, isOnHold, canStartDischarge, onOpenDischarge }: CommandBarProps) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<DoctorCommandAction | null>(null);
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const mutation = useMutation({
    mutationFn: (command: DoctorCommandAction) => submitDoctorCommand(patientId, { action: command, target: target.trim() || undefined, reason: reason.trim(), expected_version: stateVersion }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['patient', patientId] }),
        queryClient.invalidateQueries({ queryKey: ['ward'] }),
      ]);
      close();
    },
    onError: (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
        setError('患者状态已由其他临床人员更新。请刷新详情，核对后重新提交。');
        return;
      }
      setError(cause instanceof Error ? cause.message : '命令提交失败，请稍后重试。');
    },
  });

  const open = (next: DoctorCommandAction) => { setAction(next); setTarget(''); setReason(''); setError(''); };
  const close = () => { if (!mutation.isPending) { setAction(null); setTarget(''); setReason(''); setError(''); } };
  const ready = action != null && (!commandNeedsTarget(action) || target.trim().length > 0) && (!commandRequiresReason(action) || reason.trim().length >= 5);

  return <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', pb: 0.25 }}>
    {isOnHold ? <Button size="small" variant="outlined" startIcon={<Play size={15} />} onClick={() => open('resume')} sx={{ textTransform: 'none' }}>恢复流程</Button> : <><Button size="small" variant="outlined" startIcon={<Workflow size={15} />} onClick={() => open('transfer')} sx={{ textTransform: 'none' }}>转科</Button><Button size="small" variant="outlined" startIcon={<Stethoscope size={15} />} onClick={() => open('consult')} sx={{ textTransform: 'none' }}>发起会诊</Button><Button size="small" color="warning" variant="outlined" startIcon={<Pause size={15} />} onClick={() => open('hold')} sx={{ textTransform: 'none' }}>暂停流程</Button></>}
    <Button size="small" color="success" variant={canStartDischarge ? 'contained' : 'outlined'} startIcon={<ClipboardCheck size={15} />} onClick={onOpenDischarge}>出院流程</Button>
    <Dialog open={action !== null} onClose={close} fullWidth maxWidth="xs">
      <DialogTitle>{action ? commandLabel(action) : '医生指令'}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {action && commandNeedsTarget(action) ? <TextField autoFocus label={action === 'transfer' ? '目标科室' : '会诊专科'} value={target} onChange={(event) => setTarget(event.target.value)} required disabled={mutation.isPending} /> : null}
        {action && commandRequiresReason(action) ? <TextField label="临床原因（至少 5 字）" value={reason} onChange={(event) => setReason(event.target.value)} multiline minRows={3} required disabled={mutation.isPending} /> : null}
        {action === 'resume' ? <Alert severity="info">恢复后将重新进入临床流程，请先确认暂停条件已解除。</Alert> : null}
      </DialogContent>
      <DialogActions><Button onClick={close} disabled={mutation.isPending}>取消</Button><Button variant="contained" onClick={() => action && mutation.mutate(action)} disabled={!ready || mutation.isPending} startIcon={mutation.isPending ? <CircularProgress size={14} color="inherit" /> : undefined}>{action ? commandLabel(action) : '确认'}</Button></DialogActions>
    </Dialog>
  </Box>;
}
