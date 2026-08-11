/**
 * OIDC 客户端集成 — Authorization Code + PKCE
 *
 * 负责:
 *   1. 按环境变量构建 UserManager 配置 (authority/client_id/redirect_uri)
 *   2. 登录跳转 signinRedirect / 回调处理 signinRedirectCallback / 登出 signoutRedirect
 *   3. 将 IdP 返回的 token claims 映射为前端 UserIdentity
 *   4. 提供 access token 读取 (供 API 客户端附加 Bearer)
 *
 * 简化说明:
 *   - 当前关闭 automaticSilentRenew (静默续期需要独立的 silent_redirect_uri 并注册到
 *     Keycloak client, 会改变后端约定的 redirect 契约)。access token 过期后由
 *     api-client 401 → 会话过期 → 重新走 Keycloak 登录, 医院统一登录会话存活时
 *     重新授权通常无需再次输入密码。
 *   - access token 会镜像写入 sessionStorage['zhenhu_token'], 让既有的同步
 *     header 构造逻辑 (auth-bridge) 在 oidc 模式下也能拿到 Bearer。
 */

import { UserManager, type User, type UserManagerSettings } from 'oidc-client-ts';
import {
  AUTH_MODE,
  OIDC_AUTHORITY,
  OIDC_CLIENT_ID,
  OIDC_REDIRECT_URI,
} from '@/config/api';
import type { UserIdentity } from '@/types/auth';

/** 认证模式是否为 OIDC (生产统一认证)。 */
export function isOidcMode(): boolean {
  return AUTH_MODE === 'oidc';
}

export function buildOidcSettings(): UserManagerSettings {
  return {
    authority: OIDC_AUTHORITY,
    client_id: OIDC_CLIENT_ID,
    redirect_uri: OIDC_REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile roles',
    automaticSilentRenew: false,
    loadUserInfo: true,
  };
}

let userManager: UserManager | null = null;

/** OIDC 重定向防抖标志: 同一页面只发起一次 signinRedirect。 */
let oidcRedirectStarted = false;

/** 尝试标记一次 OIDC 重定向; 已被标记则返回 false。 */
export function markOidcRedirectStarted(): boolean {
  if (oidcRedirectStarted) return false;
  oidcRedirectStarted = true;
  return true;
}

/** 测试专用: 复位重定向防抖标志。 */
export function resetOidcRedirectGuardForTest(): void {
  oidcRedirectStarted = false;
}

export function getUserManager(): UserManager {
  if (!userManager) userManager = new UserManager(buildOidcSettings());
  return userManager;
}

/** 测试专用: 重置单例, 可注入 mock 实例。 */
export function resetUserManagerForTest(manager: UserManager | null = null): void {
  userManager = manager;
}

/** 将 token 镜像写入 sessionStorage, 供同步的 auth-bridge 构造 Bearer header。 */
export function syncTokenMirror(token: string | null): void {
  if (token) sessionStorage.setItem('zhenhu_token', token);
  else sessionStorage.removeItem('zhenhu_token');
}

/**
 * 从 token claims 中提取角色集合 (对齐后端 auth.py 的解析规则):
 * 支持 roles / role / realm_access.roles / resource_access.*.roles。
 */
export function extractRoles(claims: Record<string, unknown>): string[] {
  const collected: unknown[] = [claims.roles, claims.role];
  const realmAccess = claims.realm_access as { roles?: unknown } | undefined;
  if (realmAccess?.roles) collected.push(realmAccess.roles);
  const resourceAccess = claims.resource_access as Record<string, { roles?: unknown }> | undefined;
  if (resourceAccess) {
    for (const resource of Object.values(resourceAccess)) {
      if (resource?.roles) collected.push(resource.roles);
    }
  }
  return collected
    .flatMap((value) => {
      if (typeof value === 'string') return value.split(',').map((part) => part.trim()).filter(Boolean);
      if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
      return [];
    })
    .map((value) => value.toLowerCase());
}

export function resolveRole(roles: string[]): 'doctor' | 'nurse' {
  if (roles.includes('doctor') || roles.includes('clinician') || roles.includes('physician')) return 'doctor';
  if (roles.includes('nurse') || roles.includes('nursing')) return 'nurse';
  return 'doctor';
}

/** 将 IdP claims 映射为前端 UserIdentity (与后端 authenticate_bearer_token 语义一致)。 */
export function mapProfileToIdentity(profile: Record<string, unknown>): UserIdentity {
  const roles = extractRoles(profile);
  const departmentValues = [profile.department, profile.departments].flatMap((value) => {
    if (typeof value === 'string') return value.split(',').map((part) => part.trim());
    if (Array.isArray(value)) return value.map((item) => String(item).trim());
    return [];
  });
  const department = departmentValues.find((value) => value.length > 0) ?? '';
  const subject = typeof profile.sub === 'string' ? profile.sub : '';
  const preferredName = typeof profile.preferred_username === 'string' ? profile.preferred_username.trim() : '';
  const displayName = typeof profile.name === 'string' && profile.name.trim() ? profile.name.trim() : preferredName;
  const title = typeof profile.title === 'string' ? profile.title.trim() : '';

  return {
    name: displayName || subject || '未知用户',
    role: resolveRole(roles),
    title,
    department,
    actor_id: subject || undefined,
    job_number: subject || undefined,
  };
}

export function mapOidcUserToIdentity(user: User): UserIdentity {
  return mapProfileToIdentity(user.profile as unknown as Record<string, unknown>);
}

/** OIDC 登录: 重定向到 Keycloak 授权端点 (Authorization Code + PKCE)。 */
export async function loginWithOidc(): Promise<void> {
  await getUserManager().signinRedirect();
}

/** 处理授权回调: 换取 token 并映射为用户身份。 */
export async function processOidcCallback(): Promise<{ identity: UserIdentity; token: string }> {
  const manager = getUserManager();
  const user = await manager.signinRedirectCallback();
  const token = user?.access_token ?? '';
  if (!token) throw new Error('统一认证回调未返回访问令牌');
  syncTokenMirror(token);
  return { identity: mapOidcUserToIdentity(user), token };
}

/** 读取当前 access token (UserManager 存储), 并同步镜像。 */
export async function getOidcAccessToken(): Promise<string | null> {
  const manager = getUserManager();
  const user = await manager.getUser();
  const token = user?.access_token ?? null;
  if (token) syncTokenMirror(token);
  return token;
}

/** OIDC 登出: 清理本地会话并重定向到 IdP 端会话端点。 */
export async function logoutOidc(): Promise<void> {
  const manager = getUserManager();
  await manager.removeUser();
  await manager.signoutRedirect();
}
