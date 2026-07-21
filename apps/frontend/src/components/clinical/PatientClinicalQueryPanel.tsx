import { useState } from 'react';
import { Alert, Box, Button, Card, CircularProgress, TextField, Typography } from '@mui/material';
import { Search } from 'lucide-react';
import { useMutation } from '@tanstack/react-query';

import { queryPatient } from '@/services/patient-service';
import type { PatientQueryResponse } from '@/types/patient-dashboard';

const QUICK_QUESTIONS = [
  '当前最需要优先处理的风险是什么？',
  '本轮查房需要重点核对哪些数据？',
  '最近检验和体征有哪些重要变化？',
  '目前是否具备出院条件，阻塞项是什么？',
];

export default function PatientClinicalQueryPanel({ patientId }: { patientId: string }) {
  const [question, setQuestion] = useState('');
  const mutation = useMutation({ mutationFn: (value: string) => queryPatient(patientId, value.trim()) });
  const result = mutation.data;
  const ask = (value: string) => {
    const normalized = value.trim();
    if (!normalized || mutation.isPending) return;
    setQuestion(normalized);
    mutation.mutate(normalized);
  };
  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', gap: 0.75, alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}><Search size={18} /><Typography variant="subtitle2" fontWeight={600}>患者状态快速查询</Typography></Box>
    <Box component="form" onSubmit={(event) => { event.preventDefault(); ask(question); }} sx={{ p: 1.75 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.25 }}>{QUICK_QUESTIONS.map((item) => <Button key={item} type="button" size="small" variant="outlined" disabled={mutation.isPending} onClick={() => ask(item)} sx={{ justifyContent: 'flex-start', textAlign: 'left' }}>{item}</Button>)}</Box>
      <TextField label="临床问题" value={question} onChange={(event) => setQuestion(event.target.value)} multiline minRows={2} maxRows={4} fullWidth placeholder="输入患者风险、趋势、用药或出院条件问题" disabled={mutation.isPending} />
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}><Button type="submit" size="small" variant="contained" disabled={!question.trim() || mutation.isPending} startIcon={mutation.isPending ? <CircularProgress size={14} color="inherit" /> : <Search size={15} />}>{mutation.isPending ? '查询中...' : '查询患者状态'}</Button></Box>
      {mutation.error ? <Alert severity="error" sx={{ mt: 1.25 }}>{mutation.error instanceof Error ? mutation.error.message : '临床查询失败'}</Alert> : null}{result ? <QueryResult result={result} /> : null}
    </Box>
  </Card>;
}

function QueryResult({ result }: { result: PatientQueryResponse }) {
  return <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px solid', borderColor: 'divider' }}><Typography variant="caption" color="text.secondary">{result.question}</Typography><Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{result.answer}</Typography>{result.citations.length ? <Box sx={{ mt: 1.25 }}><Typography variant="caption" color="text.secondary">本次回答引用</Typography>{result.citations.map((citation, index) => <Box key={`${String(citation.citation_id ?? citation.source ?? 'citation')}-${index}`} sx={{ mt: 0.5, borderLeft: '2px solid', borderColor: 'divider', pl: 0.75 }}><Typography variant="caption" fontWeight={600}>{String(citation.title ?? citation.source ?? `引用 ${index + 1}`)}</Typography><Typography variant="caption" color="text.secondary" display="block">{String(citation.excerpt ?? citation.content ?? citation.citation ?? '未提供引用片段')}</Typography></Box>)}</Box> : null}</Box>;
}
