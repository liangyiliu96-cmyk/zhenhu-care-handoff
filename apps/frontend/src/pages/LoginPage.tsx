import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Box, Button, Card, Chip, Collapse, Divider, Stack, TextField, Typography } from '@mui/material';
import { ArrowLeft, CheckCircle2, ChevronDown, ClipboardCheck, HeartPulse, LockKeyhole, LogIn, ShieldCheck, Stethoscope, UsersRound, Wrench } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { AUTH_MODE, DEV_SHORTCUT_LOGIN_ENABLED } from '@/config/api';
import { defaultRouteFor, isManagementUser } from '@/core/default-route';
import { loginModeDescription, normalizeLoginMode, supportsCredentialLogin } from '@/core/login-mode';
import { loginWithOidc } from '@/core/oidc';
import { ROUTES } from '@/core/routes';
import { useAuthStore } from '@/stores/auth-store';
import type { UserIdentity } from '@/types/auth';

const credentialsSchema = z.object({
  jobNumber: z.string().trim().min(1, '请输入工号').max(32, '工号过长'),
  password: z.string().min(1, '请输入密码').max(128, '密码过长'),
});
type Credentials = z.infer<typeof credentialsSchema>;
type DevIdentity = UserIdentity & { shortcutId: string };

const DEV_IDENTITIES: DevIdentity[] = [
  { name: '沈仲卿', role: 'doctor', title: '科主任', department: '心内科', actor_id: 'dev-doc-shen', shortcutId: 'cardiology-director' },
  { name: '陆明泽', role: 'doctor', title: '主治医师', department: '心内科', actor_id: 'dev-doc-lu', shortcutId: 'cardiology-attending-1' },
  { name: '叶知秋', role: 'doctor', title: '主治医师', department: '心内科', actor_id: 'dev-doc-ye', shortcutId: 'cardiology-attending-2' },
  { name: '宋慧敏', role: 'nurse', title: '护士长', department: '心内科', actor_id: 'dev-nurse-song', shortcutId: 'cardiology-head-nurse' },
  { name: '温雅婷', role: 'nurse', title: '主管护师', department: '心内科', actor_id: 'dev-nurse-wen', shortcutId: 'cardiology-charge-nurse' },
  { name: '聂怀远', role: 'doctor', title: '科主任', department: '呼吸科', actor_id: 'dev-doc-nie', shortcutId: 'respiratory-director' },
  { name: '霍子谦', role: 'doctor', title: '主治医师', department: '呼吸科', actor_id: 'dev-doc-huo', shortcutId: 'respiratory-attending' },
  { name: '白敬修', role: 'doctor', title: '住院医师', department: '呼吸科', actor_id: 'dev-doc-bai', shortcutId: 'respiratory-resident' },
  { name: '柳莺燕', role: 'nurse', title: '护士长', department: '呼吸科', actor_id: 'dev-nurse-liu', shortcutId: 'respiratory-head-nurse' },
  { name: '阮青禾', role: 'nurse', title: '主管护师', department: '呼吸科', actor_id: 'dev-nurse-ruan', shortcutId: 'respiratory-charge-nurse' },
];

const accessPrinciples = [
  { label: '身份验证', detail: '工号、令牌或医院统一认证', icon: <LockKeyhole size={17} /> },
  { label: '科室隔离', detail: '仅访问授权病区与患者信息', icon: <ShieldCheck size={17} /> },
  { label: '操作留痕', detail: '临床写入进入可追溯审计记录', icon: <ClipboardCheck size={17} /> },
];

const workspaceRoles = [
  { label: '医生', detail: '患者工作台', icon: <Stethoscope size={15} />, tone: '#216a7b' },
  { label: '护士', detail: '班次护理工作台', icon: <HeartPulse size={15} />, tone: '#557a4e' },
  { label: '管理者', detail: '科室管理端', icon: <UsersRound size={15} />, tone: '#b3623d' },
];

function modeMeta(mode: ReturnType<typeof normalizeLoginMode>) {
  if (mode === 'oidc') return { label: '医院统一认证', color: 'success' as const, action: '使用医院账号登录' };
  if (mode === 'jwt') return { label: '令牌认证', color: 'info' as const, action: '验证并进入系统' };
  return { label: '开发联调认证', color: 'warning' as const, action: '选择开发身份' };
}

export default function LoginPage() {
  const navigate = useNavigate();
  const mode = normalizeLoginMode(AUTH_MODE);
  const meta = modeMeta(mode);
  const login = useAuthStore((state) => state.login);
  const loginWithDevShortcut = useAuthStore((state) => state.loginWithDevShortcut);
  const setIdentity = useAuthStore((state) => state.setIdentity);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const [submitError, setSubmitError] = useState('');
  const [showDevIdentities, setShowDevIdentities] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<Credentials>({ resolver: zodResolver(credentialsSchema) });

  const onSubmit = async (value: Credentials) => {
    setSubmitError('');
    try { navigate(await login(value.jobNumber, value.password), { replace: true }); }
    catch (error) { setSubmitError(error instanceof Error ? error.message : '登录失败，请稍后重试'); }
  };
  const canUseDevShortcuts = mode === 'header' || (mode === 'jwt' && DEV_SHORTCUT_LOGIN_ENABLED);
  const handleDevIdentity = async (identity: DevIdentity) => {
    setSubmitError('');
    try {
      if (mode === 'header') {
        setIdentity(identity);
        navigate(defaultRouteFor(identity), { replace: true });
        return;
      }
      navigate(await loginWithDevShortcut(identity.shortcutId), { replace: true });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '快捷登录失败，请使用工号密码登录。');
    }
  };
  const startOidc = async () => {
    setSubmitError('');
    try {
      await loginWithOidc();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '无法跳转至医院统一认证。');
    }
  };

  return <Box sx={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(420px, 0.88fr) minmax(560px, 1.12fr)' }, bgcolor: '#f4f8f7' }}>
    <Box component="aside" sx={{ display: { xs: 'none', lg: 'flex' }, flexDirection: 'column', justifyContent: 'space-between', p: 5, bgcolor: '#e7f1ee', borderRight: '1px solid #d3e2de', color: '#183c42' }}>
      <Box><Stack direction="row" spacing={1.25} alignItems="center"><Box sx={{ width: 38, height: 38, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: '#216a7b', color: '#fff', fontWeight: 700 }}>臻</Box><Box><Typography sx={{ fontFamily: 'var(--font-display)', fontSize: 23, fontWeight: 500, lineHeight: 1 }}>臻护</Typography><Typography variant="caption">全病程数智医护平台</Typography></Box></Stack><Box sx={{ mt: 8, maxWidth: 420 }}><Typography variant="overline" sx={{ color: '#216a7b', fontWeight: 700, letterSpacing: '0.08em' }}>受控临床访问</Typography><Typography sx={{ mt: 1, fontFamily: 'var(--font-display)', fontSize: 35, lineHeight: 1.26, fontWeight: 500 }}>让每次交接，都延续患者的完整病程。</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 2.5, lineHeight: 1.85 }}>系统会依据您的角色、职务和科室确定工作入口与数据范围。临床判断与最终签署始终由授权人员完成。</Typography></Box></Box>
      <Box><Divider sx={{ mb: 2.5, borderColor: '#cadeda' }} /><Stack spacing={2}>{accessPrinciples.map((item) => <Stack key={item.label} direction="row" spacing={1.25} alignItems="flex-start"><Box sx={{ color: '#216a7b', mt: 0.15 }}>{item.icon}</Box><Box><Typography variant="body2" fontWeight={700}>{item.label}</Typography><Typography variant="caption" color="text.secondary">{item.detail}</Typography></Box></Stack>)}</Stack><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 4 }}>临床写操作采用状态版本校验，并保留完整审计记录。</Typography></Box>
    </Box>

    <Box sx={{ minHeight: '100%', display: 'flex', flexDirection: 'column', p: { xs: 2, sm: 3, lg: 5 } }}>
      <Box sx={{ width: '100%', maxWidth: 500, mx: 'auto', display: { xs: 'flex', lg: 'none' }, alignItems: 'center', gap: 1.25, mb: { xs: 4, sm: 6 } }}><Box sx={{ width: 34, height: 34, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: '#216a7b', color: '#fff', fontWeight: 700 }}>臻</Box><Typography sx={{ fontFamily: 'var(--font-display)', fontSize: 20 }}>臻护</Typography></Box>
      <Box sx={{ width: '100%', maxWidth: 500, mx: 'auto' }}>
        <Button color="inherit" size="small" startIcon={<ArrowLeft size={15} />} onClick={() => navigate(ROUTES.home)} sx={{ mb: 4, ml: -1, color: 'text.secondary' }}>返回首页</Button>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.25 }}><Typography component="h1" sx={{ fontFamily: 'var(--font-display)', fontSize: 31, fontWeight: 500 }}>身份验证</Typography><Chip size="small" label={meta.label} color={meta.color} variant="outlined" sx={{ borderRadius: 1 }} /></Stack>
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.75, mb: 3 }}>{loginModeDescription(mode)}</Typography>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', mb: 2.5, borderTop: '1px solid #d9e6e2', borderLeft: '1px solid #d9e6e2', bgcolor: '#fff' }}>
          {workspaceRoles.map((role) => <Box key={role.label} sx={{ p: 1.25, borderRight: '1px solid #d9e6e2', borderBottom: '1px solid #d9e6e2' }}><Box sx={{ color: role.tone, display: 'flex', mb: 0.5 }}>{role.icon}</Box><Typography variant="caption" fontWeight={700} sx={{ display: 'block' }}>{role.label}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.45 }}>{role.detail}</Typography></Box>)}
        </Box>

        {isAuthenticated && user ? <Alert severity="success" icon={<CheckCircle2 size={18} />} sx={{ mb: 2.5, borderRadius: 1, alignItems: 'center' }} action={<Button color="success" size="small" onClick={() => navigate(defaultRouteFor(user))}>进入工作台</Button>}>当前会话：{user.name} · {user.title} · {user.department}</Alert> : null}

        <Card variant="outlined" sx={{ borderRadius: 1, borderColor: '#cddeda', boxShadow: '0 10px 28px rgba(22, 69, 75, 0.07)' }}>
          <Box sx={{ p: { xs: 2.5, sm: 3.5 } }}><Stack spacing={2.5}><Box><Stack direction="row" spacing={1} alignItems="center"><Stethoscope size={19} color="#216a7b" /><Typography variant="subtitle1" fontWeight={700}>安全进入系统</Typography></Stack><Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, lineHeight: 1.65 }}>验证成功后将按工号绑定的角色、职务和科室进入独立工作区。</Typography></Box>{submitError ? <Alert severity="error" onClose={() => setSubmitError('')}>{submitError}</Alert> : null}
            {supportsCredentialLogin(mode) ? <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}><Stack spacing={2}><TextField label="工号" autoComplete="username" autoFocus error={Boolean(errors.jobNumber)} helperText={errors.jobNumber?.message} {...register('jobNumber')} fullWidth /><TextField label="密码" type="password" autoComplete="current-password" error={Boolean(errors.password)} helperText={errors.password?.message} {...register('password')} fullWidth /><Button type="submit" variant="contained" size="large" fullWidth disabled={isLoading} startIcon={<LogIn size={18} />} sx={{ minHeight: 46, borderRadius: 1, bgcolor: '#216a7b', boxShadow: 'none', '&:hover': { bgcolor: '#185766', boxShadow: 'none' } }}>{isLoading ? '正在验证身份...' : meta.action}</Button></Stack></Box> : <Button variant="contained" size="large" fullWidth onClick={() => void startOidc()} startIcon={<LockKeyhole size={18} />} sx={{ minHeight: 48, borderRadius: 1, bgcolor: '#216a7b', boxShadow: 'none', '&:hover': { bgcolor: '#185766', boxShadow: 'none' } }}>{isLoading ? '正在跳转...' : meta.action}</Button>}</Stack></Box>
          {canUseDevShortcuts ? <><Divider /><Box sx={{ p: 1.25 }}><Button color="inherit" fullWidth disabled={isLoading} onClick={() => setShowDevIdentities((value) => !value)} endIcon={<ChevronDown size={15} style={{ transform: showDevIdentities ? 'rotate(180deg)' : undefined, transition: 'transform 160ms ease' }} />} startIcon={<Wrench size={15} />} sx={{ justifyContent: 'space-between', borderRadius: 0.75, textTransform: 'none', color: '#35555a' }}><Typography variant="body2" fontWeight={700}>本地快捷登录</Typography><Chip label={`${DEV_IDENTITIES.length} 位`} size="small" sx={{ height: 22, borderRadius: 1 }} /></Button><Collapse in={showDevIdentities}><Box sx={{ mt: 1, pt: 1, borderTop: '1px solid #e3ece9' }}><Typography variant="caption" color="text.secondary" sx={{ px: 1, display: 'block', mb: 1 }}>{mode === 'jwt' ? '快捷身份由本地后端签发 JWT，仅在显式开发开关开启时可用。' : '仅用于本地 Header 联调。其他科室请使用工号和密码完成身份验证。'}</Typography>{DEV_IDENTITIES.map((identity) => <Button key={identity.actor_id} color="inherit" fullWidth disabled={isLoading} onClick={() => void handleDevIdentity(identity)} sx={{ justifyContent: 'flex-start', textTransform: 'none', borderRadius: 0.75, px: 1.25, py: 1 }}><Box sx={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: 1, mr: 1.25, bgcolor: identity.role === 'doctor' ? '#e7f1f3' : '#ebf2e8', color: identity.role === 'doctor' ? '#216a7b' : '#557a4e', fontSize: 12, fontWeight: 700 }}>{identity.name[0]}</Box><Box sx={{ textAlign: 'left', flex: 1 }}><Typography variant="body2" fontWeight={700}>{identity.name}</Typography><Typography variant="caption" color="text.secondary">{identity.title} · {identity.department}</Typography></Box>{isManagementUser(identity) ? <Chip label="管理端" size="small" color="info" sx={{ borderRadius: 1, height: 20 }} /> : null}</Button>)}</Box></Collapse></Box></> : null}
        </Card>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2.5, lineHeight: 1.65 }}>继续操作即表示您确认已获得相应授权。请勿共享账号或在非受控设备上保存会话。</Typography>
      </Box>
      <Box sx={{ mt: 'auto', pt: 4, width: '100%', maxWidth: 500, mx: 'auto', display: 'flex', justifyContent: 'space-between', color: 'text.secondary' }}><Typography variant="caption">臻护 · 全病程数智医护平台</Typography><Typography variant="caption">受控访问</Typography></Box>
    </Box>
  </Box>;
}
