import { Alert, Box, Card, Chip, Divider, Typography } from '@mui/material';
import { ShieldAlert } from 'lucide-react';

import type { MedicationExternalEvidence, MedicationSafety, MedicationSafetyConflict } from '@/types/patient-dashboard';

interface MedicationSafetyPanelProps {
  safety: MedicationSafety;
}

const severityLabels: Record<string, string> = {
  contraindicated: '禁忌',
  major: '严重',
  moderate: '中等',
  minor: '轻微',
};

function severityColor(severity: string): 'error' | 'warning' | 'default' {
  if (severity === 'contraindicated' || severity === 'major') return 'error';
  if (severity === 'moderate') return 'warning';
  return 'default';
}

export default function MedicationSafetyPanel({ safety }: MedicationSafetyPanelProps) {
  const externalEvidence = safety.external_evidence ?? [];
  const hasFindings = safety.conflicts.length > 0 || safety.allergy_contraindications.length > 0 || safety.gaps.length > 0 || safety.duplications.length > 0 || safety.warnings.length > 0 || externalEvidence.length > 0;

  return <Card variant="outlined" sx={{ borderRadius: 1 }}>
    <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
      <ShieldAlert size={18} />
      <Typography variant="subtitle2" fontWeight={600}>用药安全核对</Typography>
    </Box>
    <Box sx={{ p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {safety.status !== 'complete' ? <Alert severity="info">尚未完成患者级用药核对，当前不展示“无相互作用”结论。</Alert> : null}
      {safety.status === 'complete' && !hasFindings ? <Typography variant="body2" color="text.secondary">已完成核对，未发现已记录的相互作用、过敏禁忌、用药缺口或重复用药。</Typography> : null}
      {safety.conflicts.map((conflict, index) => <ConflictItem key={`${conflict.drug_pair}-${index}`} conflict={conflict} />)}
      {safety.allergy_contraindications.map((item, index) => <Box key={`${item.medication}-${item.allergen}-${index}`} sx={{ borderLeft: '3px solid', borderColor: 'error.main', pl: 1.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{item.medication} / {item.allergen}</Typography><Chip size="small" color={severityColor(item.severity)} label={severityLabels[item.severity] || item.severity} /></Box>
        {item.recommendation ? <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.4 }}>{item.recommendation}</Typography> : null}
        <Typography variant="caption" color="text.secondary">依据：已记录过敏史核对</Typography>
      </Box>)}
      {safety.gaps.map((item, index) => <FindingItem key={`gap-${index}`} label="用药缺口" text={item} />)}
      {safety.duplications.map((item, index) => <FindingItem key={`duplicate-${index}`} label="潜在重复" text={item} />)}
      {safety.warnings.map((item, index) => <FindingItem key={`warning-${index}`} label="需复核" text={item} />)}
      {externalEvidence.length > 0 ? <ExternalEvidenceSection evidence={externalEvidence} /> : null}
    </Box>
  </Card>;
}

function ExternalEvidenceSection({ evidence }: { evidence: MedicationExternalEvidence[] }) {
  const available = evidence.filter((item) => item.status === 'available');

  return <Box sx={{ pt: 0.25 }}>
    <Divider sx={{ mb: 1.25 }} />
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap', mb: 0.8 }}>
      <Typography variant="subtitle2" fontWeight={600}>外部药品证据</Typography>
      <Chip size="small" variant="outlined" label="仅供医生复核" />
    </Box>
    {available.length === 0 ? <Alert severity="info" sx={{ py: 0 }}>外部药品证据暂不可用，未据此得出安全结论。</Alert> : available.map((item, index) => <Box key={`${item.drug}-${item.rxnorm_id}-${index}`} sx={{ borderLeft: '3px solid', borderColor: 'info.main', pl: 1.25, mb: index === available.length - 1 ? 0 : 1.1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
        <Typography variant="body2" fontWeight={600}>{item.drug}</Typography>
        {item.standard_name ? <Chip size="small" variant="outlined" label={item.standard_name} /> : null}
        {item.rxnorm_id ? <Chip size="small" variant="outlined" label={`RxCUI ${item.rxnorm_id}`} /> : null}
        <Chip size="small" color="info" label={item.source} />
      </Box>
      {item.warnings ? <Typography variant="caption" display="block" sx={{ mt: 0.4 }}>标签警告：{item.warnings}</Typography> : null}
      {item.contraindications ? <Typography variant="caption" display="block" color="text.secondary">禁忌信息：{item.contraindications}</Typography> : null}
      {item.interactions ? <Typography variant="caption" display="block" color="text.secondary">相互作用标签：{item.interactions}</Typography> : null}
    </Box>)}
    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.8 }}>仅供医生复核，不自动生成医嘱。</Typography>
  </Box>;
}

function ConflictItem({ conflict }: { conflict: MedicationSafetyConflict }) {
  return <Box sx={{ borderLeft: '3px solid', borderColor: severityColor(conflict.severity) === 'error' ? 'error.main' : 'warning.main', pl: 1.25 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{conflict.drug_pair}</Typography><Chip size="small" color={severityColor(conflict.severity)} label={severityLabels[conflict.severity] || conflict.severity} />{conflict.model_suggested ? <Chip size="small" variant="outlined" label="需临床复核" /> : null}</Box>
    {conflict.consequence ? <Typography variant="caption" display="block" sx={{ mt: 0.4 }}>{conflict.consequence}</Typography> : null}
    {conflict.mechanism ? <Typography variant="caption" color="text.secondary" display="block">机制：{conflict.mechanism}</Typography> : null}
    {conflict.recommendation ? <Typography variant="caption" color="text.secondary" display="block">建议：{conflict.recommendation}</Typography> : null}
    <Typography variant="caption" color="text.secondary">依据：{conflict.source}{conflict.evidence ? ` · 证据等级 ${conflict.evidence}` : ''}</Typography>
  </Box>;
}

function FindingItem({ label, text }: { label: string; text: string }) {
  return <Box><Divider sx={{ mb: 1.25 }} /><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2">{text}</Typography></Box>;
}
