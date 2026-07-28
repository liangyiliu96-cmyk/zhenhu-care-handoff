import { Badge, Box, Card, Chip, Tab, Tabs, Typography } from '@mui/material';
import { ArrowRight, Brain, Building, Gauge, ListOrdered, Siren } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { patientRoute } from '@/core/routes';
const I_PASS_SEVERITY: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'default' }> = {
  critical: { label: '不稳定', color: 'error' },
  high:     { label: '需关注', color: 'warning' },
  medium:   { label: '稳定', color: 'default' },
  low:      { label: '稳定', color: 'success' },
};
const RISK_ORDER = ['critical', 'high', 'medium', 'low'];

interface PatientSummary {
  patient_id: string;
  name?: string | null;
  disease?: string | null;
  phase?: string | null;
  risk_level?: string | null;
  round_count?: number | null;
  has_pending_review?: boolean | null;
  pending_review_type?: string | null;
  alert_count?: number | null;
  discharge_decision?: string | null;
}

interface Props {
  patients: PatientSummary[];
  total: number;
}

export default function WorkbenchSmartPanel({ patients, total }: Props) {
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);

  const { visitOrder, dischargeReady, needingAttention } = useMemo(() => {
    const sorted = [...patients].sort((a, b) => {
      const ra = RISK_ORDER.indexOf(a.risk_level ?? 'low');
      const rb = RISK_ORDER.indexOf(b.risk_level ?? 'low');
      if (ra !== rb) return ra - rb;
      return (b.alert_count ?? 0) - (a.alert_count ?? 0);
    });

    const discharge = patients.filter((p) =>
      p.phase && ['discharge', 'handoff', 'confirm'].some((v) => (p.phase ?? '').includes(v))
    );

    const attention = patients.filter((p) =>
      p.has_pending_review || p.risk_level === 'critical' || p.risk_level === 'high' || (p.alert_count ?? 0) > 0
    );

    return { visitOrder: sorted, dischargeReady: discharge, needingAttention: attention };
  }, [patients]);

  if (!patients.length) return null;

  const tabs = [
    { label: '查房顺序', icon: <ListOrdered size={15} />, count: visitOrder.length, highlight: visitOrder.slice(0, 5) },
    { label: `待关注 (${needingAttention.length})`, icon: <Siren size={15} />, count: needingAttention.length, highlight: needingAttention.slice(0, 5) },
    { label: `即将出院 (${dischargeReady.length})`, icon: <Building size={15} />, count: dischargeReady.length, highlight: dischargeReady.slice(0, 5) },
  ];

  const current = tabs[tab];

  return (
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 2, py: 1.2, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Gauge size={17} />
        <Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>智能工作面板</Typography>
        <Typography variant="caption" color="text.secondary">共 {total} 人</Typography>
        <Chip size="small" icon={<Brain size={13} />} label="AI 排序" color="primary" variant="outlined" />
      </Box>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: '1px solid', borderColor: 'divider', minHeight: 40, '& .MuiTab-root': { minHeight: 40, py: 0.5, px: 1.5 } }}
      >
        {tabs.map((t, i) => (
          <Tab key={i} label={t.label} icon={t.icon} iconPosition="start" sx={{ textTransform: 'none', fontSize: 13 }} />
        ))}
      </Tabs>

      <Box sx={{ p: current.highlight.length ? 0 : 2 }}>
        {current.highlight.length ? (
          current.highlight.map((p, i) => (
            <PatientRow
              key={p.patient_id}
              index={tab === 0 ? i + 1 : undefined}
              patient={p}
              showRisk={tab === 0 || tab === 1}
              onClick={() => navigate(patientRoute(p.patient_id))}
            />
          ))
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
            {tab === 0 ? '所有患者状态平稳，无特殊排序建议' : tab === 1 ? '当前无高风险或待审核患者' : '当前无即将出院患者'}
          </Typography>
        )}
        {current.count > 5 && (
          <Box sx={{ px: 1.5, py: 1, display: 'flex', justifyContent: 'flex-end' }}>
            <Chip size="small" label={`共 ${current.count} 人，显示前 5`} variant="outlined" />
          </Box>
        )}
      </Box>
    </Card>
  );
}

function PatientRow({ index, patient, showRisk, onClick }: { index?: number; patient: PatientSummary; showRisk: boolean; onClick: () => void }) {
  const risk = patient.risk_level ?? 'low';
  const hasReview = patient.has_pending_review;
  const hasAlerts = (patient.alert_count ?? 0) > 0;

  return (
    <Box
      onClick={onClick}
      sx={{
        px: 1.5, py: 0.75,
        display: 'flex', alignItems: 'center', gap: 1.2,
        cursor: 'pointer',
        borderBottom: '1px solid',
        borderColor: 'divider',
        '&:hover': { bgcolor: 'action.hover' },
        '&:last-child': { borderBottom: 0 },
      }}
    >
      {index ? (
        <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: index <= 3 ? 'primary.main' : 'grey.400', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
          {index}
        </Box>
      ) : null}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{patient.name ?? patient.patient_id}</Typography>
          {hasReview && <Badge color="warning" variant="dot" sx={{ '& .MuiBadge-badge': { position: 'static', transform: 'none' } }} />}
          {hasAlerts && <Badge color="error" variant="dot" sx={{ '& .MuiBadge-badge': { position: 'static', transform: 'none' } }} />}
        </Box>
        <Box sx={{ display: 'flex', gap: 0.75, mt: 0.15 }}>
          <Typography variant="caption" color="text.secondary">{patient.disease ?? '未标注'}</Typography>
          {patient.round_count ? <Typography variant="caption" color="text.disabled">{patient.round_count}轮查房</Typography> : null}
        </Box>
      </Box>
      {showRisk && (
        <Chip size="small" color={I_PASS_SEVERITY[risk]?.color ?? 'default'} label={I_PASS_SEVERITY[risk]?.label ?? risk} sx={{ height: 22, fontSize: 11, flexShrink: 0 }} />
      )}
      <ArrowRight size={15} color="#bbb" style={{ flexShrink: 0 }} />
    </Box>
  );
}
