import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2 } from 'lucide-react';

import { ApiClientError } from '@/core/api-client';
import { completeNursingTask } from '@/services/nurse-management-service';
import type { NurseTask, NursingTaskItem } from '@/types/nurse-management';

export interface NursingTaskSelection {
  patient: NurseTask;
  task: NursingTaskItem;
}

export default function NursingTaskCompletionDialog({
  selection,
  onClose,
}: {
  selection: NursingTaskSelection | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const idempotencyKey = useMemo(() => selection ? createIdempotencyKey(selection) : '', [selection]);
  const mutation = useMutation({
    mutationFn: () => completeNursingTask(selection!.patient.patient_id, {
      task_type: selection!.task.task_type,
      task_key: selection!.task.task_key,
      note: note.trim(),
      expected_version: selection!.patient.state_version,
    }, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['nurse'] }),
        queryClient.invalidateQueries({ queryKey: ['ward'] }),
        queryClient.invalidateQueries({ queryKey: ['patient', selection!.patient.patient_id] }),
      ]);
      onClose();
    },
    onError: async (cause) => {
      if (cause instanceof ApiClientError && cause.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ['nurse', 'tasks'] });
      }
    },
  });

  useEffect(() => {
    setNote('');
    mutation.reset();
    // Reset the form only when a different server-derived task is selected.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection?.task.task_key]);

  const error = mutation.error instanceof ApiClientError && mutation.error.status === 409
    ? mutation.error.message
    : mutation.error instanceof Error ? mutation.error.message : '';

  return <Dialog open={Boolean(selection)} onClose={mutation.isPending ? undefined : onClose} fullWidth maxWidth="xs">
    <DialogTitle>完成护理任务</DialogTitle>
    <DialogContent sx={{ pt: '12px !important' }}>
      <Stack spacing={1.5}>
        {error ? <Alert severity="warning">{error}</Alert> : null}
        {selection ? <>
          <Typography variant="subtitle2" fontWeight={600}>{selection.patient.name} · {selection.task.title}</Typography>
          <Typography variant="body2" color="text.secondary">{selection.task.description}</Typography>
        </> : null}
        {selection?.task.task_type === 'vital_signs' ? <Alert severity="info">完成任务只记录执行审计，不会代替体征数据录入。请先保存实际测量值。</Alert> : null}
        <TextField
          autoFocus
          label="执行备注"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          multiline
          minRows={3}
          placeholder="记录执行结果、异常情况或交接要点"
          inputProps={{ maxLength: 1000 }}
        />
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button onClick={onClose} disabled={mutation.isPending}>取消</Button>
      <Button
        variant="contained"
        onClick={() => mutation.mutate()}
        disabled={!selection || mutation.isPending}
        startIcon={mutation.isPending ? <CircularProgress size={15} color="inherit" /> : <CheckCircle2 size={16} />}
      >确认完成</Button>
    </DialogActions>
  </Dialog>;
}

function createIdempotencyKey(selection: NursingTaskSelection): string {
  const suffix = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `nursing-task:${selection.patient.patient_id}:${selection.task.task_key}:${suffix}`.slice(0, 100);
}
