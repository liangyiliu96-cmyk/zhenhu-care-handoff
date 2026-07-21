import { create } from 'zustand';
import type { UserIdentity } from '@/types/auth';
import { fetchWhoami, loginWithCredentials, loginWithDevShortcut } from '@/services/auth-service';
import { setDevIdentity, clearIdentity } from '@/core/auth-bridge';
import { AUTH_MODE } from '@/config/api';
import { defaultRouteFor } from '@/core/default-route';

interface AuthState {
  user: UserIdentity | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  /** 通过工号+密码登录 (dev/jwt 模式) */
  login: (jobNumber: string, password: string) => Promise<string>;
  loginWithDevShortcut: (shortcutId: string) => Promise<string>;

  /** 通过当前身份信息直接设置 (header 模式) */
  setIdentity: (identity: UserIdentity) => void;

  /** 验证当前身份 (OIDC 回调后 / dev 启动时) */
  verifySession: () => Promise<void>;

  /** 登出 */
  logout: () => void;
}

function storedIdentity(): UserIdentity | null {
  const role = sessionStorage.getItem('zhenhu_role');
  if (role !== 'doctor' && role !== 'nurse') return null;
  return {
    name: sessionStorage.getItem('zhenhu_name') ?? '',
    role,
    title: sessionStorage.getItem('zhenhu_title') ?? '',
    department: sessionStorage.getItem('zhenhu_department') ?? '',
    actor_id: sessionStorage.getItem('zhenhu_actor_id') ?? undefined,
    job_number: sessionStorage.getItem('zhenhu_actor_id') ?? undefined,
  };
}

const initialUser = storedIdentity();

function applyLoginResponse(res: Awaited<ReturnType<typeof loginWithCredentials>>, set: (state: Partial<AuthState>) => void) {
  const user: UserIdentity = {
    name: res.name,
    role: res.role,
    title: res.title,
    department: res.department,
    actor_id: res.job_number,
    job_number: res.job_number,
  };
  setDevIdentity({
    role: res.role,
    title: res.title,
    department: res.department,
    name: res.name,
    actorId: res.job_number,
    token: res.token,
  });
  set({ user, token: res.token, isAuthenticated: true, isLoading: false, error: null });
  return defaultRouteFor(user);
}

export const useAuthStore = create<AuthState>((set) => ({
  user: initialUser,
  token: sessionStorage.getItem('zhenhu_token'),
  isAuthenticated: Boolean(initialUser),
  isLoading: false,
  error: null,

  login: async (jobNumber: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await loginWithCredentials(jobNumber, password);
      return applyLoginResponse(res, set);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '登录失败';
      set({ isLoading: false, error: msg });
      throw err;
    }
  },

  loginWithDevShortcut: async (shortcutId: string) => {
    set({ isLoading: true, error: null });
    try {
      return applyLoginResponse(await loginWithDevShortcut(shortcutId), set);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '快捷登录失败';
      set({ isLoading: false, error: msg });
      throw err;
    }
  },

  setIdentity: (identity: UserIdentity) => {
    setDevIdentity({
      role: identity.role,
      title: identity.title,
      department: identity.department,
        name: identity.name,
        actorId: identity.actor_id,
    });
    set({ user: identity, isAuthenticated: true, error: null });
  },

  verifySession: async () => {
    if (AUTH_MODE === 'header') {
      try {
        const user = await fetchWhoami();
        set({ user, isAuthenticated: true, error: null });
      } catch {
        set({ user: null, isAuthenticated: false });
      }
      return;
    }
    const token = sessionStorage.getItem('zhenhu_token');
    if (!token) {
      set({ user: null, isAuthenticated: false });
      return;
    }
    try {
      const user = await fetchWhoami();
      set({ user, token, isAuthenticated: true, error: null });
    } catch {
      clearIdentity();
      set({ user: null, token: null, isAuthenticated: false });
    }
  },

  logout: () => {
    clearIdentity();
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },
}));
