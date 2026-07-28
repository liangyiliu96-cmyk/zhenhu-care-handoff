import { Box, ButtonBase, Card, Chip, Divider, Typography } from '@mui/material';
import {
  Activity,
  ArrowRight,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  HeartPulse,
  LockKeyhole,
  SearchCheck,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';

import type { PendingResponse } from '@/types/ward';

interface DoctorWorkflowCockpitProps {
  patientCount: number;
  pending: PendingResponse['summary'];
  alerts: number;
  highRisk: number;
  dischargeReady: number;
  onOpenRounds: () => void;
  onOpenReview: () => void;
  onOpenAlerts: () => void;
  onOpenDischarge: () => void;
  onOpenFollowUp: () => void;
}

type Tone = 'info' | 'warning' | 'error' | 'success' | 'default';

const TONE_STYLES: Record<Tone, { color: string; background: string }> = {
  info: { color: 'info.dark', background: 'info.light' },
  warning: { color: 'warning.dark', background: 'warning.light' },
  error: { color: 'error.dark', background: 'error.light' },
  success: { color: 'success.dark', background: 'success.light' },
  default: { color: 'text.secondary', background: 'action.hover' },
};

export default function DoctorWorkflowCockpit({
  patientCount,
  pending,
  alerts,
  highRisk,
  dischargeReady,
  onOpenRounds,
  onOpenReview,
  onOpenAlerts,
  onOpenDischarge,
  onOpenFollowUp,
}: DoctorWorkflowCockpitProps) {
  const reviewCount = pending.total_items ?? 0;
  const lanes = [
    { label: '病区状态', value: patientCount, suffix: '人在院', icon: HeartPulse, tone: 'info' as Tone, onClick: onOpenRounds },
    { label: '预查房', value: highRisk + alerts, suffix: '例优先核对', icon: Stethoscope, tone: highRisk || alerts ? 'warning' as Tone : 'success' as Tone, onClick: onOpenRounds },
    { label: '医生确认', value: reviewCount, suffix: '项待审核', icon: ClipboardCheck, tone: reviewCount ? 'error' as Tone : 'success' as Tone, onClick: onOpenReview },
    { label: '出院协同', value: dischargeReady, suffix: '例可推进', icon: CheckCircle2, tone: dischargeReady ? 'success' as Tone : 'default' as Tone, onClick: onOpenDischarge },
    { label: '出院随访', value: '→', suffix: '进入后续管理', icon: ArrowRight, tone: 'default' as Tone, onClick: onOpenFollowUp },
  ];

  const agents = [
    { label: '病区状态归并', detail: `${patientCount} 位患者的阶段、告警与待办已汇总`, source: '规则优先', tone: patientCount ? 'success' as Tone : 'default' as Tone, icon: Activity, onClick: onOpenRounds },
    { label: '告警与风险处置', detail: alerts ? `${alerts} 条未解决告警等待进入患者处置` : '当前没有新的未解决告警', source: '规则优先', tone: alerts ? 'error' as Tone : 'success' as Tone, icon: Activity, onClick: onOpenAlerts },
    { label: '查房与风险摘要', detail: highRisk ? `${highRisk} 位高风险患者需要医生核对本轮变化` : '当前没有新的高风险患者', source: 'Agent + RAG', tone: highRisk ? 'warning' as Tone : 'success' as Tone, icon: SearchCheck, onClick: onOpenRounds },
    { label: '用药安全与审核', detail: pending.med_pending ? `${pending.med_pending} 项用药调整等待医生确认` : '未触发用药审核卡点', source: '证据门禁', tone: pending.med_pending ? 'error' as Tone : 'default' as Tone, icon: ShieldCheck, onClick: onOpenReview },
    { label: '出院交接链路', detail: dischargeReady ? `${dischargeReady} 位患者可以进入出院协同` : '等待出院条件达标后推进', source: '人工签署', tone: dischargeReady ? 'success' as Tone : 'default' as Tone, icon: FileCheck2, onClick: onOpenDischarge },
  ];

  return (
    <Card variant="outlined" sx={{ overflow: 'hidden', borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1.35, display: 'flex', alignItems: 'flex-start', gap: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ width: 34, height: 34, display: 'grid', placeItems: 'center', bgcolor: 'primary.main', color: 'primary.contrastText', borderRadius: 1, flexShrink: 0 }}><Bot size={18} /></Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2">临床协同引擎</Typography>
            <Chip size="small" variant="outlined" color="info" label="规则 + RAG + LLM + 医生确认" />
          </Box>
          <Typography variant="caption" color="text.secondary">把今天的患者处置串成一条路径；模型只生成有证据的摘要和草稿，临床写入仍由医生完成。</Typography>
        </Box>
      </Box>

      <Box sx={{ px: 1.75, py: 1.25, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Typography variant="overline" color="text.secondary">医生主路径</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(5, minmax(0, 1fr))' }, gap: 0.75, mt: 0.5 }}>
          {lanes.map((lane, index) => {
            const Icon = lane.icon;
            const tone = TONE_STYLES[lane.tone];
            return <ButtonBase key={lane.label} onClick={lane.onClick} sx={{ display: 'block', textAlign: 'left', borderRadius: 1, minWidth: 0, '&:hover > .MuiBox-root': { borderColor: 'primary.main', bgcolor: 'action.hover' } }}>
              <Box sx={{ minHeight: 94, p: 1.05, border: '1px solid', borderColor: 'divider', bgcolor: index === 0 ? 'rgba(11, 100, 114, 0.035)' : 'background.paper' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: tone.color }}><Icon size={16} /><Typography variant="caption" color="text.secondary">0{index + 1}</Typography></Box>
                <Typography variant="body2" fontWeight={700} sx={{ mt: 1 }}>{lane.label}</Typography>
                <Typography variant="h6" sx={{ mt: 0.25, color: tone.color }}>{lane.value}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap>{lane.suffix}</Typography>
              </Box>
            </ButtonBase>;
          })}
        </Box>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.35fr) minmax(300px, 0.65fr)' } }}>
        <Box sx={{ p: 1.75 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 1 }}><Activity size={16} /><Typography variant="subtitle2">当前能力状态</Typography><Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>病区级</Typography></Box>
          <Box sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
            {agents.map((agent) => <ButtonBase key={agent.label} onClick={agent.onClick} sx={{ width: '100%', display: 'block', textAlign: 'left', borderBottom: '1px solid', borderColor: 'divider', '&:hover': { bgcolor: 'action.hover' } }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: '30px minmax(0, 1fr) auto', gap: 1, alignItems: 'center', py: 1.05 }}>
                <Box sx={{ width: 26, height: 26, display: 'grid', placeItems: 'center', bgcolor: TONE_STYLES[agent.tone].background, color: TONE_STYLES[agent.tone].color, borderRadius: 0.75 }}><agent.icon size={15} /></Box>
                <Box sx={{ minWidth: 0 }}><Typography variant="body2" fontWeight={650}>{agent.label}</Typography><Typography variant="caption" color="text.secondary" noWrap>{agent.detail}</Typography></Box>
                <Chip size="small" variant="outlined" color={agent.tone === 'default' ? 'default' : agent.tone} label={agent.source} />
              </Box>
            </ButtonBase>)}
          </Box>
        </Box>

        <Box sx={{ p: 1.75, bgcolor: 'rgba(11, 100, 114, 0.025)', borderLeft: { lg: '1px solid' }, borderTop: { xs: '1px solid', lg: 0 }, borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.65, mb: 1 }}><LockKeyhole size={16} /><Typography variant="subtitle2">安全边界</Typography></Box>
          <GuardrailStep index="01" title="先用规则筛选" detail="风险、阶段和排序由确定性规则控制。" icon={<Activity size={15} />} />
          <GuardrailStep index="02" title="再查证据" detail="需要知识时才查询 RAG，并保留引用。" icon={<SearchCheck size={15} />} />
          <GuardrailStep index="03" title="生成可编辑草稿" detail="LLM 只负责摘要、解释和待确认内容。" icon={<Bot size={15} />} />
          <GuardrailStep index="04" title="医生确认后写入" detail="审核、签字和正式记录不会被模型越权执行。" icon={<ShieldCheck size={15} />} last />
        </Box>
      </Box>

      <Divider />
      <Box sx={{ px: 1.75, py: 0.9, display: 'flex', alignItems: 'center', gap: 0.6, bgcolor: 'action.hover' }}><Stethoscope size={14} /><Typography variant="caption" color="text.secondary">患者级 Agent 的证据、调用次数、超时、回退与待审核卡点，请进入患者详情的“临床概览 / 查房管理”查看。</Typography></Box>
    </Card>
  );
}

function GuardrailStep({ index, title, detail, icon, last = false }: { index: string; title: string; detail: string; icon: React.ReactNode; last?: boolean }) {
  return <Box sx={{ display: 'grid', gridTemplateColumns: '24px minmax(0, 1fr)', gap: 0.8, position: 'relative', pb: last ? 0 : 1.15 }}>
    {!last ? <Box sx={{ position: 'absolute', left: 11, top: 22, bottom: 1, width: 1, bgcolor: 'divider' }} /> : null}
    <Box sx={{ width: 24, height: 24, display: 'grid', placeItems: 'center', zIndex: 1, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', color: 'primary.main', borderRadius: 0.75 }}>{icon}</Box>
    <Box sx={{ minWidth: 0 }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.55 }}><Typography variant="caption" fontWeight={700} color="primary.dark">{index}</Typography><Typography variant="body2" fontWeight={650}>{title}</Typography></Box><Typography variant="caption" color="text.secondary">{detail}</Typography></Box>
  </Box>;
}
