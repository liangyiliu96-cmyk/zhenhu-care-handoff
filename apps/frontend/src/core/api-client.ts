/**
 * 统一 API 客户端
 *
 * 职责:
 *   1. 解包 UnifiedResponse.data
 *   2. 如果 UnifiedResponse.error 存在 → 抛出 ApiError
 *   3. 统一处理 401/403/409/5xx
 *   4. 自动注入认证 headers (header/jwt/oidc)
 *   5. 超时控制
 */

import { API_BASE, API_TIMEOUT_READ, API_TIMEOUT_WRITE } from '@/config/api';
import type { UnifiedResponse } from '@/types/api';
import { getAuthHeaders } from './auth-bridge';
import { emitAuthExpired } from './runtime-events';

class ApiClientError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
  }
}

/** 将服务端错误转换为临床工作区可以直接展示的提示。 */
export function describeApiError(error: unknown, fallback = '请求失败，请稍后重试') {
  if (!(error instanceof ApiClientError)) return error instanceof Error ? error.message : fallback;
  if (error.code === 'FORBIDDEN') return '当前账号无权访问该患者或该功能，请确认所在科室和角色。';
  if (error.code === 'NOT_FOUND') return '未找到对应记录，可能已被归档或已过期。';
  if (error.code === 'STATE_VERSION_CONFLICT') return '患者状态已被更新，请刷新后重新核对再提交。';
  if (error.code === 'TIMEOUT') return '服务响应超时，数据未必已提交，请先重试或刷新确认。';
  return error.message || fallback;
}

export function resolveApiUrl(path: string, apiBase = API_BASE): string {
  const normalizedBase = apiBase.trim().replace(/\/+$/, '');
  if (!normalizedBase) return path;

  return `${normalizedBase}${path.startsWith('/') ? path : `/${path}`}`;
}

async function request<T>(
  path: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const { timeout, ...fetchOptions } = options;
  const url = resolveApiUrl(path);

  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    timeout || API_TIMEOUT_READ
  );

  try {
    const method = fetchOptions.method || 'GET';
    const hasBody = method !== 'GET' && method !== 'HEAD' && method !== 'DELETE';
    const headers: Record<string, string> = {
      ...getAuthHeaders(),
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...((fetchOptions.headers as Record<string, string>) || {}),
    };

    const res = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!res.ok) {
      if (res.status === 401) {
        emitAuthExpired();
        throw new ApiClientError(401, 'UNAUTHORIZED', '会话已过期，请重新登录');
      }
      if (res.status === 403) {
        throw new ApiClientError(403, 'FORBIDDEN', '无该功能访问权限');
      }
      if (res.status === 404) {
        throw new ApiClientError(404, 'NOT_FOUND', '资源不存在');
      }
      if (res.status === 409) {
        const body = await res.json().catch(() => ({}));
        throw new ApiClientError(
          409,
          'STATE_VERSION_CONFLICT',
          (body as UnifiedResponse).error?.message || (body as { detail?: string }).detail || '数据已被他人更新，请刷新后重试'
        );
      }
      const body = await res.json().catch(() => ({}));
      throw new ApiClientError(
        res.status,
        (body as UnifiedResponse).error?.code || 'SERVER_ERROR',
        (body as UnifiedResponse).error?.message || (body as { detail?: string }).detail || `服务器错误 (${res.status})`
      );
    }

    const unified: UnifiedResponse<T> = await res.json();

    if (unified.error) {
      throw new ApiClientError(
        res.status,
        unified.error.code,
        unified.error.message
      );
    }

    return unified.data as T;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof ApiClientError) throw err;
    if ((err as Error).name === 'AbortError') {
      throw new ApiClientError(0, 'TIMEOUT', '请求超时，请检查网络后重试');
    }
    throw new ApiClientError(0, 'NETWORK_ERROR', '无法连接服务器');
  }
}

// 便捷方法
export async function apiGet<T>(path: string, timeout = API_TIMEOUT_READ) {
  return request<T>(path, { method: 'GET', timeout });
}

export async function apiPost<T>(path: string, body?: unknown, timeout = API_TIMEOUT_WRITE, headers?: Record<string, string>) {
  return request<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
    timeout,
    headers,
  });
}

export async function apiPatch<T>(path: string, body?: unknown, headers?: Record<string, string>) {
  return request<T>(path, {
    method: 'PATCH',
    body: body ? JSON.stringify(body) : undefined,
    timeout: API_TIMEOUT_WRITE,
    headers,
  });
}

export async function apiDelete<T>(path: string) {
  return request<T>(path, { method: 'DELETE', timeout: API_TIMEOUT_WRITE });
}

export { ApiClientError };
