import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from 'react';
import { Alert, Box, Button, Snackbar, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { AUTH_EXPIRED_EVENT, NOTIFICATION_EVENT, type NotificationDetail } from '@/core/runtime-events';
import { ROUTES } from '@/core/routes';
import { useAuthStore } from '@/stores/auth-store';

export function AppRuntimeGuards({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<NotificationDetail | null>(null);

  useEffect(() => {
    const onExpired = () => {
      useAuthStore.getState().logout();
      queryClient.clear();
      setNotice({ severity: 'warning', message: '会话已过期，请重新登录。' });
      navigate(ROUTES.login, { replace: true });
    };
    const onNotice = (event: Event) => setNotice((event as CustomEvent<NotificationDetail>).detail);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener(NOTIFICATION_EVENT, onNotice);
    return () => { window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired); window.removeEventListener(NOTIFICATION_EVENT, onNotice); };
  }, [navigate, queryClient]);

  return <><AppErrorBoundary>{children}</AppErrorBoundary><Snackbar open={Boolean(notice)} autoHideDuration={5000} onClose={() => setNotice(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}><Alert severity={notice?.severity ?? 'info'} onClose={() => setNotice(null)} variant="filled">{notice?.message}</Alert></Snackbar></>;
}

class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Logging is owned by the deployment observability layer. */ }
  render() {
    if (!this.state.failed) return this.props.children;
    return <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 3 }}><Box sx={{ maxWidth: 460 }}><Alert severity="error" sx={{ mb: 2 }}>页面出现异常，当前临床数据未被修改。</Alert><Button variant="contained" onClick={() => window.location.reload()}>刷新页面</Button></Box></Box>;
  }
}

/** 面板级错误边界——单面板崩溃只影响自身，不炸整页。 */
export class PanelErrorBoundary extends Component<{ children: ReactNode; name?: string }, { failed: boolean; message: string }> {
  state = { failed: false, message: '' };
  static getDerivedStateFromError(error: Error) { return { failed: true, message: error.message.slice(0, 200) }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Alert severity="warning" sx={{ m: 1 }}>
        {this.props.name ?? '面板'}加载异常
        {this.state.message ? <Typography variant="caption" display="block">{this.state.message}</Typography> : null}
      </Alert>
    );
  }
}
