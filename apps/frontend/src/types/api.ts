/**
 * 后端 UnifiedResponse<T> 范型
 * 所有 API 响应都包裹在此结构中: { data: T } 或 { error: { code, message }, data: null }
 */
export interface UnifiedResponse<T = unknown> {
  data: T | null;
  error?: {
    code: string;
    message: string;
  };
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
}

export function isApiError(obj: unknown): obj is ApiError {
  return typeof obj === 'object' && obj !== null && 'status' in obj && 'code' in obj;
}
