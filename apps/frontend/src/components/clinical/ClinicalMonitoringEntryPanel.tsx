import { useState } from 'react';
import { Alert, Box, Button, Card, CircularProgress, Tab, Tabs, TextField, Typography } from '@mui/material';
import { Activity, FlaskConical, Save } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import { reportLabResult, reportVitalSigns } from '@/services/patient-service';

interface ClinicalMonitoringEntryPanelProps {
  patientId: string;
  stateVersion: number;
}

type EntryMode = 'vitals' | 'lab';

export default function ClinicalMonitoringEntryPanel({ patientId, stateVersion }: ClinicalMonitoringEntryPanelProps) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<EntryMode>('vitals');
  const [systolic, setSystolic] = useState('');
  const [diastolic, setDiastolic] = useState('');
  const [heartRate, setHeartRate] = useState('');
  const [spo2, setSpo2] = useState('');
  const [temperature, setTemperature] = useState('');
  const [labName, setLabName] = useState('');
  const [labValue, setLabValue] = useState('');
  const [labUnit, setLabUnit] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const mutation = useMutation({
    mutationFn: async () => {
      setError('');
      setSuccess('');
      if (mode === 'vitals') {
        const payload = buildVitalPayload({ systolic, diastolic, heartRate, spo2, temperature, stateVersion });
        return reportVitalSigns(patientId, payload);
      }
      if (!labName.trim() || !labValue.trim()) throw new Error('请填写检验项目和结果');
      return reportLabResult(patientId, {
        name: labName.trim(), value: labValue.trim(), unit: labUnit.trim(), expected_version: stateVersion,
      });
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['patient', patientId] }),
        queryClient.invalidateQueries({ queryKey: ['ward'] }),
      ]);
      if (mode === 'vitals') {
        setSystolic(''); setDiastolic(''); setHeartRate(''); setSpo2(''); setTemperature('');
      } else {
        setLabName(''); setLabValue(''); setLabUnit('');
      }
      const pending = Boolean((result as { pending_review?: boolean }).pending_review);
      setSuccess(pending ? '数据已记录，并触发新的医生审核待办。' : '临床数据已记录，相关趋势和风险评估已刷新。');
    },
    onError: (cause) => {
      if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
        setError('患者状态已由其他人员更新，请刷新患者页面后重新提交。');
        return;
      }
      setError(cause instanceof Error ? cause.message : '临床数据提交失败');
    },
  });

  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, pt: 1.25, display: 'flex', alignItems: 'center', gap: 0.75 }}>
      {mode === 'vitals' ? <Activity size={18} /> : <FlaskConical size={18} />}
      <Typography variant="subtitle2" fontWeight={600}>临床数据录入</Typography>
    </Box>
    <Tabs value={mode} onChange={(_, value: EntryMode) => { setMode(value); setError(''); setSuccess(''); }} sx={{ px: 1 }}>
      <Tab value="vitals" label="生命体征" />
      <Tab value="lab" label="检验结果" />
    </Tabs>
    <Box sx={{ p: 1.75, pt: 1.25, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {success ? <Alert severity="success">{success}</Alert> : null}
      {mode === 'vitals' ? <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(5, minmax(0, 1fr))' }, gap: 1 }}>
        <TextField label="收缩压" value={systolic} onChange={(event) => setSystolic(event.target.value)} type="number" slotProps={{ htmlInput: { min: 50, max: 300 } }} />
        <TextField label="舒张压" value={diastolic} onChange={(event) => setDiastolic(event.target.value)} type="number" slotProps={{ htmlInput: { min: 20, max: 200 } }} />
        <TextField label="心率" value={heartRate} onChange={(event) => setHeartRate(event.target.value)} type="number" slotProps={{ htmlInput: { min: 20, max: 300 } }} />
        <TextField label="SpO₂" value={spo2} onChange={(event) => setSpo2(event.target.value)} type="number" slotProps={{ htmlInput: { min: 50, max: 100 } }} />
        <TextField label="体温" value={temperature} onChange={(event) => setTemperature(event.target.value)} type="number" slotProps={{ htmlInput: { min: 34, max: 43, step: 0.1 } }} />
      </Box> : <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(180px, 1.2fr) minmax(120px, 0.8fr) minmax(100px, 0.6fr)' }, gap: 1 }}>
        <TextField label="检验项目" value={labName} onChange={(event) => setLabName(event.target.value)} placeholder="例如：钾、肌酐、血红蛋白" />
        <TextField label="结果" value={labValue} onChange={(event) => setLabValue(event.target.value)} />
        <TextField label="单位" value={labUnit} onChange={(event) => setLabUnit(event.target.value)} placeholder="mmol/L" />
      </Box>}
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button variant="contained" onClick={() => mutation.mutate()} disabled={mutation.isPending} startIcon={mutation.isPending ? <CircularProgress size={15} color="inherit" /> : <Save size={16} />}>
          记录{mode === 'vitals' ? '体征' : '检验'}
        </Button>
      </Box>
    </Box>
  </Card>;
}

function buildVitalPayload(values: { systolic: string; diastolic: string; heartRate: string; spo2: string; temperature: string; stateVersion: number }) {
  const hasSystolic = values.systolic.trim() !== '';
  const hasDiastolic = values.diastolic.trim() !== '';
  if (hasSystolic !== hasDiastolic) throw new Error('血压需要同时填写收缩压和舒张压');
  if (![values.systolic, values.diastolic, values.heartRate, values.spo2, values.temperature].some((value) => value.trim())) {
    throw new Error('请至少填写一项生命体征');
  }
  return {
    timestamp: new Date().toISOString(),
    ...(hasSystolic ? {
      systolic_mmhg: Number(values.systolic),
      diastolic_mmhg: Number(values.diastolic),
      blood_pressure: `${Number(values.systolic)}/${Number(values.diastolic)}`,
    } : {}),
    ...(values.heartRate.trim() ? { heart_rate: Number(values.heartRate) } : {}),
    ...(values.spo2.trim() ? { spo2: Number(values.spo2) } : {}),
    ...(values.temperature.trim() ? { temperature: Number(values.temperature) } : {}),
    expected_version: values.stateVersion,
  };
}
