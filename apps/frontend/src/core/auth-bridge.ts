/**
 * 认证桥接 — 支持 header / jwt / oidc 三模式
 *
 * header: dev 模式，设 x-role/x-title/x-department headers
 * jwt:    联调模式，从 authStore.token 设 Authorization: Bearer
 * oidc:   生产模式，从 OIDC 回调获取 token，同上 Bearer
 */

import { AUTH_MODE } from '@/config/api';

export function encodeAuthHeaderValue(value: string): string {
  return encodeURIComponent(value);
}

export function getAuthMode(): string {
  return AUTH_MODE;
}

/** 从会话镜像读取 Bearer token (jwt/oidc 模式由登录流程写入)。 */
export function getBearerToken(): string | null {
  return sessionStorage.getItem('zhenhu_token');
}

export function getAuthHeaders(): Record<string, string> {
  if (AUTH_MODE === 'jwt' || AUTH_MODE === 'oidc') {
    const token = getBearerToken();
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
    return {};
  }

  // header 模式: 从 sessionStorage 读取开发身份
  const role = sessionStorage.getItem('zhenhu_role') || 'doctor';
  const actorId = sessionStorage.getItem('zhenhu_actor_id');
  const name = sessionStorage.getItem('zhenhu_name');
  const title = sessionStorage.getItem('zhenhu_title') || '主治医师';
  const department = sessionStorage.getItem('zhenhu_department') || '心内科';

  return {
    'x-role': role,
    ...(actorId ? { 'x-user-id': actorId } : {}),
    ...(name ? { 'x-user-name': encodeAuthHeaderValue(name) } : {}),
    'x-title': encodeAuthHeaderValue(title),
    'x-department': encodeAuthHeaderValue(department),
  };
}

export function setDevIdentity(identity: {
  role: string;
  title: string;
  department: string;
  actorId?: string;
  name?: string;
  token?: string;
}) {
  sessionStorage.setItem('zhenhu_role', identity.role);
  sessionStorage.setItem('zhenhu_title', identity.title);
  sessionStorage.setItem('zhenhu_department', identity.department);
  if (identity.actorId) sessionStorage.setItem('zhenhu_actor_id', identity.actorId);
  if (identity.name) sessionStorage.setItem('zhenhu_name', identity.name);
  if (identity.token) sessionStorage.setItem('zhenhu_token', identity.token);
}

export function clearIdentity() {
  sessionStorage.removeItem('zhenhu_role');
  sessionStorage.removeItem('zhenhu_title');
  sessionStorage.removeItem('zhenhu_department');
  sessionStorage.removeItem('zhenhu_actor_id');
  sessionStorage.removeItem('zhenhu_name');
  sessionStorage.removeItem('zhenhu_token');
}
