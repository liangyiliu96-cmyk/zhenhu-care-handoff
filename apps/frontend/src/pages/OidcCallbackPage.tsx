import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { isOidcMode } from '@/core/oidc';
import { ROUTES } from '@/core/routes';
import { useAuthStore } from '@/stores/auth-store';

/**
 * OIDC 授权回调页 (/callback)。
 * 处理 Authorization Code + PKCE 回调, 建立本地会话后跳转到用户默认工作区。
 */
export default function OidcCallbackPage() {
  const navigate = useNavigate();
  const completeOidcLogin = useAuthStore((state) => state.completeOidcLogin);
  const [error, setError] = useState('');
  const [processing, setProcessing] = useState(true);

  useEffect(() => {
    let active = true;
    if (!isOidcMode()) {
      setProcessing(false);
      setError('当前未启用医院统一认证模式。');
      return () => {
        active = false;
      };
    }
    completeOidcLogin()
      .then((route) => {
        if (active) navigate(route, { replace: true });
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : '统一认证处理失败，请重试。');
        setProcessing(false);
      });
    return () => {
      active = false;
    };
  }, [completeOidcLogin, navigate]);

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 3, bgcolor: '#f4f8f7' }}>
      <Box sx={{ maxWidth: 420, width: '100%', textAlign: 'center' }}>
        {processing && !error ? (
          <>
            <CircularProgress size={36} sx={{ mb: 2, color: '#216a7b' }} />
            <Typography variant="h6" sx={{ fontFamily: 'var(--font-display)' }}>正在完成统一身份认证...</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>正在建立安全会话，请稍候。</Typography>
          </>
        ) : null}
        {error ? (
          <>
            <Alert severity="error" sx={{ mb: 2, borderRadius: 1 }}>{error}</Alert>
            <Button variant="contained" onClick={() => navigate(ROUTES.login)} sx={{ borderRadius: 1, bgcolor: '#216a7b', '&:hover': { bgcolor: '#185766' } }}>
              返回登录
            </Button>
          </>
        ) : null}
      </Box>
    </Box>
  );
}
