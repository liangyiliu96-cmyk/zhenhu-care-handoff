import { useEffect } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { defaultRouteFor, isManagementUser } from '@/core/default-route';
import { ROUTES } from '@/core/routes';
import { isOidcMode, loginWithOidc, markOidcRedirectStarted, resetOidcRedirectGuardForTest } from '@/core/oidc';
import type { ReactNode } from 'react';

interface RequireAuthProps {
  children: ReactNode;
  role?: 'doctor' | 'nurse';
  adminOnly?: boolean;
  departmentScoped?: boolean;
}

function getFallbackUser() {
  const stored = sessionStorage.getItem('zhenhu_role');
  if (!stored) return null;
  return {
    name: sessionStorage.getItem('zhenhu_name') ?? '',
    role: (stored as 'doctor' | 'nurse') || 'doctor',
    title: sessionStorage.getItem('zhenhu_title') ?? '',
    department: sessionStorage.getItem('zhenhu_department') ?? '',
  };
}

export default function RequireAuth({ children, role, adminOnly, departmentScoped = false }: RequireAuthProps) {
  const { user: storeUser, isAuthenticated } = useAuthStore();
  const { department: routeDepartment } = useParams();

  const user = storeUser ?? getFallbackUser();
  const authed = isAuthenticated || !!sessionStorage.getItem('zhenhu_role');

  // oidc 模式: 未登录时自动重定向到医院统一认证
  useEffect(() => {
    if (isOidcMode() && !authed && markOidcRedirectStarted()) {
      void loginWithOidc().catch(() => {
        resetOidcRedirectGuardForTest();
      });
    }
  }, [authed]);

  if (!authed || !user) {
    if (isOidcMode()) return null; // 等待 signinRedirect 完成跳转
    return <Navigate to={ROUTES.login} replace />;
  }

  if (role && user.role !== role && !adminOnly) {
    return <Navigate to={defaultRouteFor(user)} replace />;
  }

  if (adminOnly && !isManagementUser(user)) return <Navigate to={defaultRouteFor(user)} replace />;

  if (departmentScoped && routeDepartment !== user.department) {
    return <Navigate to={defaultRouteFor(user)} replace />;
  }

  return <>{children}</>;
}
