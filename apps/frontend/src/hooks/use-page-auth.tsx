import { Navigate } from 'react-router-dom';
import { defaultRouteFor, isManagementUser } from '@/core/default-route';

export interface AuthUser {
  name: string;
  role: 'doctor' | 'nurse';
  title: string;
  department: string;
}

export function usePageAuth(requiredRole?: 'doctor' | 'nurse') {
  const role = sessionStorage.getItem('zhenhu_role');
  const name = sessionStorage.getItem('zhenhu_name');
  const title = sessionStorage.getItem('zhenhu_title');
  const department = sessionStorage.getItem('zhenhu_department');

  if (!role) {
    return { user: null, redirect: <Navigate to="/" replace /> };
  }

  const user: AuthUser = {
    name: name ?? '',
    role: role as 'doctor' | 'nurse',
    title: title ?? '',
    department: department ?? '',
  };

  if (requiredRole && user.role !== requiredRole) {
    const fallback = defaultRouteFor(user);
    return { user: null, redirect: <Navigate to={fallback} replace /> };
  }

  return { user, redirect: null };
}

export function useManagementPageAuth() {
  const auth = usePageAuth();
  if (auth.redirect || !auth.user) return auth;
  if (!isManagementUser(auth.user)) {
    return { user: null, redirect: <Navigate to={defaultRouteFor(auth.user)} replace /> };
  }
  return auth;
}
