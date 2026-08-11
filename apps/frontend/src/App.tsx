import { Routes, Route, Navigate } from 'react-router-dom';
import { Component, Suspense, lazy, type ErrorInfo, type ReactNode } from 'react';
import { Box, Button, CircularProgress, Typography } from '@mui/material';
import { ROUTES } from '@/core/routes';
import RequireAuth from '@/core/require-auth';

const LoginPage = lazy(() => import('@/pages/LoginPage'));
const OidcCallbackPage = lazy(() => import('@/pages/OidcCallbackPage'));
const HomePage = lazy(() => import('@/pages/HomePage'));
const WorkbenchPage = lazy(() => import('@/pages/WorkbenchPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const DischargePage = lazy(() => import('@/pages/DischargePage'));
const NurseBoardPage = lazy(() => import('@/pages/NurseBoardPage'));
const AdminPage = lazy(() => import('@/pages/AdminPage'));

function PageFallback() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
      <CircularProgress size={32} />
    </Box>
  );
}

class RouteErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Route rendering failed', error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 3, bgcolor: 'background.default' }}><Box sx={{ maxWidth: 440, textAlign: 'center' }}><Typography variant="h5">页面暂时无法加载</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 1, lineHeight: 1.7 }}>当前操作没有提交。请重试加载；若问题持续，请重新进入对应工作区。</Typography><Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mt: 2.5 }}><Button variant="outlined" onClick={() => this.setState({ hasError: false })}>重试</Button><Button variant="contained" onClick={() => window.location.assign('/')}>返回首页</Button></Box></Box></Box>;
  }
}

export default function App() {
  return (
    <RouteErrorBoundary><Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path={ROUTES.home} element={<HomePage />} />
        <Route path={ROUTES.login} element={<LoginPage />} />
        <Route path={ROUTES.callback} element={<OidcCallbackPage />} />
        <Route path={ROUTES.workbench} element={<RequireAuth role="doctor"><WorkbenchPage /></RequireAuth>} />
        <Route path={ROUTES.patientTemplate} element={<RequireAuth role="doctor"><DashboardPage /></RequireAuth>} />
        <Route path={ROUTES.dischargeTemplate} element={<RequireAuth role="doctor"><DischargePage /></RequireAuth>} />
        <Route path={ROUTES.nurse} element={<RequireAuth role="nurse"><NurseBoardPage /></RequireAuth>} />
        <Route path={ROUTES.admin} element={<RequireAuth adminOnly><AdminPage /></RequireAuth>} />
        <Route path={ROUTES.departmentDoctorTemplate} element={<RequireAuth role="doctor" departmentScoped><WorkbenchPage /></RequireAuth>} />
        <Route path={ROUTES.departmentNurseTemplate} element={<RequireAuth role="nurse" departmentScoped><NurseBoardPage /></RequireAuth>} />
        <Route path={ROUTES.departmentManagementTemplate} element={<RequireAuth adminOnly departmentScoped><AdminPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
      </Routes>
    </Suspense></RouteErrorBoundary>
  );
}
