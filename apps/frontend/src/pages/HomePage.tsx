import { Box, Button, Chip, Divider, Drawer, Fab, IconButton, Stack, Tooltip, Typography } from '@mui/material';
import { Activity, ArrowRight, Bot, CheckCircle2, ClipboardCheck, FileCheck2, HeartPulse, Hospital, LockKeyhole, ShieldCheck, Stethoscope, UsersRound, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import PatientAssistantPanel from '@/components/clinical/PatientAssistantPanel';
import { AUTH_MODE } from '@/config/api';
import { defaultRouteFor } from '@/core/default-route';
import { ROUTES } from '@/core/routes';
import { useAuthStore } from '@/stores/auth-store';

const workflow = [
  { label: '入院评估', detail: '病史、体征、风险分层', icon: <Stethoscope size={18} />, tone: '#216a7b' },
  { label: '住院协同', detail: '监测、查房、护理交接', icon: <Activity size={18} />, tone: '#557a4e' },
  { label: '出院延续', detail: '审核、教育、随访闭环', icon: <ClipboardCheck size={18} />, tone: '#b3623d' },
];

const capabilities = [
  { title: '角色即权限', detail: '以医生、护士和科室管理职责组织工作入口与可见数据。', icon: <ShieldCheck size={19} />, tone: '#216a7b' },
  { title: '临床链路连续', detail: '将监测、查房、用药、护理及出院交接连成同一病程。', icon: <HeartPulse size={19} />, tone: '#b3623d' },
  { title: 'AI 辅助有边界', detail: '建议、证据与草稿都保留临床确认和审计追溯。', icon: <Bot size={19} />, tone: '#557a4e' },
];

const roleLanes = [
  { role: '医生工作台', detail: '围绕患者查看评估、查房、监测、用药与出院审核。', items: ['病程评估', '查房记录', '出院签署'], icon: <Stethoscope size={20} />, tone: '#216a7b' },
  { role: '护理工作台', detail: '按班次组织待执行护理、逾期监测与交接班重点。', items: ['班次任务', '患者详情', '交接班'], icon: <HeartPulse size={20} />, tone: '#557a4e' },
  { role: '科室管理端', detail: '为科主任和护士长集中呈现科室协同与质量信息。', items: ['病区态势', '护理核查', '知识内容'], icon: <UsersRound size={20} />, tone: '#b3623d' },
];

const culturePrinciples = [
  { title: '交接不是终点', detail: '每一次出院交接都要回答：患者回到社区后，下一位照护者能否继续理解并接住这段病程。' },
  { title: '建议必须可追溯', detail: '智能助手可以汇总证据、生成草稿和提示风险，但不能替代医生、护士的专业确认。' },
  { title: '记录服务于协同', detail: '将重要临床事实放入连续的工作流，而不是留在彼此孤立的文档和口头交班中。' },
];

const departments = ['心内科', '呼吸科', '神经内科', '肾内科', '消化内科', '内分泌科', '骨科', '老年科'];

function authModeLabel() {
  if (AUTH_MODE === 'oidc') return '医院统一认证';
  if (AUTH_MODE === 'jwt') return '令牌认证';
  return '开发联调认证';
}

export default function HomePage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const hasSession = isAuthenticated && Boolean(user);
  const primaryRoute = hasSession && user ? defaultRouteFor(user) : ROUTES.login;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: '#f3f7f6', color: '#193238' }}>
      <Box component="header" sx={{ height: 64, bgcolor: '#fff', borderBottom: '1px solid #dce7e4' }}>
        <Box sx={{ maxWidth: 1180, height: '100%', mx: 'auto', px: { xs: 2, md: 4 }, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
          <Stack direction="row" spacing={1.25} alignItems="center">
            <Box sx={{ width: 34, height: 34, display: 'grid', placeItems: 'center', bgcolor: '#216a7b', color: '#fff', borderRadius: 1, fontWeight: 700 }}>臻</Box>
            <Box>
              <Typography sx={{ fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 500, lineHeight: 1.05 }}>臻护</Typography>
              <Typography variant="caption" color="text.secondary">全病程数智医护平台</Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Stack direction="row" spacing={0.25} sx={{ display: { xs: 'none', md: 'flex' } }}>
              <Button href="#collaboration" color="inherit" size="small" sx={{ color: 'text.secondary' }}>协同方式</Button>
              <Button href="#culture" color="inherit" size="small" sx={{ color: 'text.secondary' }}>临床文化</Button>
              <Button href="#coverage" color="inherit" size="small" sx={{ color: 'text.secondary' }}>覆盖范围</Button>
            </Stack>
            <Chip icon={<LockKeyhole size={13} />} label={authModeLabel()} size="small" variant="outlined" sx={{ borderRadius: 1, bgcolor: '#fbfdfc' }} />
            {hasSession && user ? <Chip label={`${user.department} · 已认证`} size="small" color="success" sx={{ borderRadius: 1, display: { xs: 'none', sm: 'inline-flex' } }} /> : null}
          </Stack>
        </Box>
      </Box>

      <Box component="main">
        <Box sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, pt: { xs: 5, md: 8 }, pb: { xs: 4, md: 6 }, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.02fr) minmax(420px, 0.98fr)' }, gap: { xs: 4, lg: 7 }, alignItems: 'center' }}>
          <Box>
            <Typography variant="overline" sx={{ color: '#216a7b', fontWeight: 700, letterSpacing: '0.08em' }}>住院全病程协同</Typography>
            <Typography component="h1" sx={{ mt: 1, fontFamily: 'var(--font-display)', fontSize: { xs: 42, md: 58 }, lineHeight: 1.06, fontWeight: 500, color: '#17383d' }}>臻护</Typography>
            <Typography sx={{ mt: 1.5, fontSize: { xs: 22, md: 28 }, lineHeight: 1.35, fontWeight: 500, color: '#274d53' }}>全病程数智医护平台</Typography>
            <Typography sx={{ mt: 2.25, maxWidth: 590, color: 'text.secondary', fontSize: 16, lineHeight: 1.85 }}>围绕患者住院病程，将临床评估、病区协同、护理执行与出院延续统一到可追溯的工作流中。AI 提供辅助，不替代临床决策。</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} sx={{ mt: 3.5 }}>
              <Button variant="contained" size="large" onClick={() => navigate(primaryRoute)} endIcon={<ArrowRight size={18} />} sx={{ minHeight: 48, px: 3, borderRadius: 1, bgcolor: '#216a7b', boxShadow: 'none', '&:hover': { bgcolor: '#185766', boxShadow: 'none' } }}>{hasSession ? '进入当前工作台' : '进入受控登录'}</Button>
              <Button variant="outlined" size="large" onClick={() => setAssistantOpen(true)} startIcon={<Bot size={18} />} sx={{ minHeight: 48, px: 2.5, borderRadius: 1, borderColor: '#a9bfbb', color: '#294d51', '&:hover': { borderColor: '#216a7b', bgcolor: '#edf6f4' } }}>咨询健康助手</Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>仅限取得授权的医疗机构工作人员使用，临床写操作均进入审计留痕。</Typography>
          </Box>

          <Box aria-label="临床协同工作流" sx={{ border: '1px solid #cbded9', bgcolor: '#fff', borderRadius: 1, overflow: 'hidden', boxShadow: '0 10px 28px rgba(26, 69, 75, 0.08)' }}>
            <Box sx={{ px: 2.5, py: 1.75, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #e1ece9' }}>
              <Stack direction="row" spacing={1} alignItems="center"><Hospital size={18} color="#216a7b" /><Typography variant="subtitle2" fontWeight={700}>临床协同工作流</Typography></Stack>
              <Chip label="受控执行" size="small" color="success" variant="outlined" sx={{ borderRadius: 1 }} />
            </Box>
            <Box sx={{ px: 2.5, py: 2.5 }}>
              {workflow.map((item, index) => <Box key={item.label} sx={{ display: 'grid', gridTemplateColumns: '40px minmax(0, 1fr)', gap: 1.5, position: 'relative', pb: index === workflow.length - 1 ? 0 : 2.5 }}>
                {index < workflow.length - 1 ? <Box sx={{ position: 'absolute', left: 19, top: 40, bottom: 0, width: '1px', bgcolor: '#d6e5e1' }} /> : null}
                <Box sx={{ width: 40, height: 40, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: `${item.tone}12`, color: item.tone, zIndex: 1 }}>{item.icon}</Box>
                <Box sx={{ pt: 0.2 }}><Typography variant="body2" fontWeight={700}>{item.label}</Typography><Typography variant="caption" color="text.secondary">{item.detail}</Typography></Box>
              </Box>)}
            </Box>
            <Divider />
            <Box sx={{ p: 2.25, bgcolor: '#f7fbfa' }}>
              <Stack direction="row" spacing={1} alignItems="flex-start"><CheckCircle2 size={17} color="#557a4e" style={{ marginTop: 2 }} /><Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.65 }}>每一个节点都由对应角色确认，并保留状态版本、操作人员与时间记录。</Typography></Stack>
            </Box>
          </Box>
        </Box>

        <Box sx={{ borderTop: '1px solid #dce7e4', borderBottom: '1px solid #dce7e4', bgcolor: '#fff' }}>
          <Box sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, py: 4, display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: 0 }}>
            {capabilities.map((item, index) => <Box key={item.title} sx={{ px: { xs: 0, md: 3 }, py: { xs: 2, md: 0 }, borderRight: { md: index === capabilities.length - 1 ? 0 : '1px solid #e2ecea' }, borderBottom: { xs: index === capabilities.length - 1 ? 0 : '1px solid #e2ecea', md: 0 } }}>
              <Box sx={{ color: item.tone, display: 'flex', mb: 1.25 }}>{item.icon}</Box><Typography variant="subtitle2" fontWeight={700}>{item.title}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.6, lineHeight: 1.7 }}>{item.detail}</Typography>
            </Box>)}
          </Box>
        </Box>

        <Box id="collaboration" sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 5, md: 7 } }}>
          <Box sx={{ maxWidth: 650, mb: 4 }}>
            <Typography variant="overline" sx={{ color: '#216a7b', fontWeight: 700, letterSpacing: '0.08em' }}>同一病程，不同职责</Typography>
            <Typography component="h2" sx={{ mt: 0.8, fontFamily: 'var(--font-display)', fontSize: { xs: 30, md: 38 }, lineHeight: 1.25, fontWeight: 500, color: '#17383d' }}>让每个角色看到该做的事，而不是更多无关信息。</Typography>
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'repeat(3, minmax(0, 1fr))' }, gap: { xs: 1.5, lg: 0 }, border: { lg: '1px solid #d6e5e1' }, borderRadius: 1, overflow: 'hidden', bgcolor: '#fff' }}>
            {roleLanes.map((lane, index) => <Box key={lane.role} sx={{ p: 2.5, borderRight: { lg: index === roleLanes.length - 1 ? 0 : '1px solid #d6e5e1' }, border: { xs: '1px solid #d6e5e1', lg: 0 }, borderRadius: { xs: 1, lg: 0 } }}>
              <Box sx={{ width: 40, height: 40, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: `${lane.tone}12`, color: lane.tone }}>{lane.icon}</Box>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 2 }}>{lane.role}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, minHeight: 48, lineHeight: 1.7 }}>{lane.detail}</Typography>
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>{lane.items.map((item) => <Chip key={item} label={item} size="small" variant="outlined" sx={{ borderRadius: 1, bgcolor: '#fbfdfc' }} />)}</Stack>
            </Box>)}
          </Box>
        </Box>

        <Box id="culture" sx={{ bgcolor: '#244b4e', color: '#f5fbf9', borderTop: '1px solid #1d3e41', borderBottom: '1px solid #1d3e41' }}>
          <Box sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 5, md: 7 }, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(260px, 0.72fr) minmax(0, 1.28fr)' }, gap: { xs: 3.5, lg: 7 } }}>
            <Box><Stack direction="row" spacing={1} alignItems="center"><FileCheck2 size={19} color="#c8d98a" /><Typography variant="overline" sx={{ color: '#c8d98a', fontWeight: 700, letterSpacing: '0.08em' }}>我们的临床协同原则</Typography></Stack><Typography component="h2" sx={{ mt: 1.5, fontFamily: 'var(--font-display)', fontSize: { xs: 29, md: 38 }, lineHeight: 1.28, fontWeight: 500 }}>把患者的连续照护，放在每个工作选择之前。</Typography><Typography variant="body2" sx={{ mt: 2, maxWidth: 360, color: '#d6e7e4', lineHeight: 1.8 }}>这不是额外的工作负担，而是让关键临床信息在正确时间抵达正确角色的工作方式。</Typography></Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: { xs: 2.5, md: 0 } }}>{culturePrinciples.map((principle, index) => <Box key={principle.title} sx={{ px: { md: 2.5 }, borderLeft: { md: index === 0 ? 0 : '1px solid rgba(214, 231, 228, 0.22)' } }}><Typography variant="subtitle2" fontWeight={700} sx={{ color: '#fff' }}>{principle.title}</Typography><Typography variant="body2" sx={{ mt: 1, color: '#d6e7e4', lineHeight: 1.78 }}>{principle.detail}</Typography></Box>)}</Box>
          </Box>
        </Box>

        <Box id="coverage" sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 5, md: 7 } }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '0.7fr 1.3fr' }, gap: { xs: 2.5, lg: 6 }, alignItems: 'start' }}><Box><Typography variant="overline" sx={{ color: '#216a7b', fontWeight: 700, letterSpacing: '0.08em' }}>多科室协同基础</Typography><Typography component="h2" sx={{ mt: 0.8, fontFamily: 'var(--font-display)', fontSize: { xs: 29, md: 37 }, lineHeight: 1.28, fontWeight: 500, color: '#17383d' }}>临床路径随科室而变，访问边界始终清晰。</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 1.75, lineHeight: 1.8 }}>不同科室可使用对应病种模板、风险评估与护理清单；登录身份决定其患者数据与工作范围。</Typography></Box><Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', borderTop: '1px solid #d6e5e1', borderLeft: '1px solid #d6e5e1' }}>{departments.map((department) => <Box key={department} sx={{ px: 2, py: 1.6, display: 'flex', alignItems: 'center', gap: 1, borderRight: '1px solid #d6e5e1', borderBottom: '1px solid #d6e5e1', bgcolor: '#fff' }}><Hospital size={16} color="#216a7b" /><Typography variant="body2" fontWeight={600}>{department}</Typography></Box>)}</Box></Box>
        </Box>
      </Box>

      <Box component="footer" sx={{ maxWidth: 1180, mx: 'auto', px: { xs: 2, md: 4 }, py: 2.5, display: 'flex', justifyContent: 'space-between', gap: 2, color: 'text.secondary' }}><Typography variant="caption">臻护 · 全病程数智医护平台</Typography><Typography variant="caption">角色权限 · 科室隔离 · 审计追溯</Typography></Box>

      <Tooltip title="健康助手"><Fab aria-label="打开健康助手" color="primary" size="medium" onClick={() => setAssistantOpen(true)} sx={{ position: 'fixed', right: 24, bottom: 24, bgcolor: '#216a7b', boxShadow: '0 8px 20px rgba(33, 106, 123, 0.25)', '&:hover': { bgcolor: '#185766' } }}><Bot size={20} /></Fab></Tooltip>
      <HomeAssistant open={assistantOpen} onClose={() => setAssistantOpen(false)} onLogin={() => navigate(ROUTES.login)} />
    </Box>
  );
}

function HomeAssistant({ open, onClose, onLogin }: { open: boolean; onClose: () => void; onLogin: () => void }) {
  return <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 460 }, bgcolor: '#f7fbfa' } }}><Box sx={{ minHeight: '100%', p: { xs: 2, sm: 3 }, display: 'flex', flexDirection: 'column' }}><Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2.5 }}><Box><Typography variant="subtitle1" fontWeight={700}>臻护健康助手</Typography><Typography variant="caption" color="text.secondary">公共咨询，不读取患者临床数据</Typography></Box><IconButton onClick={onClose} size="small" aria-label="关闭健康助手"><X size={18} /></IconButton></Box><PatientAssistantPanel assistantMode="patient" publicAccess defaultOpen /><Box sx={{ pt: 2 }}><Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>需要查看病区信息或进行临床操作，请使用受控身份登录。</Typography><Button variant="contained" fullWidth endIcon={<ArrowRight size={16} />} onClick={onLogin} sx={{ mt: 2, borderRadius: 1, py: 1.2, bgcolor: '#216a7b', '&:hover': { bgcolor: '#185766' } }}>前往登录</Button></Box></Box></Drawer>;
}
