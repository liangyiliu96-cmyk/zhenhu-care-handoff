/**
 * API 配置常量
 */
export const API_BASE = import.meta.env.VITE_API_BASE || '';

export const API_TIMEOUT_READ = 10_000;
export const API_TIMEOUT_WRITE = 15_000;
export const API_TIMEOUT_CLINICAL = 30_000;
export const API_TIMEOUT_AGENT = 90_000;

export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE || 'header';
export const OIDC_LOGIN_URL = import.meta.env.VITE_OIDC_LOGIN_URL || '';
export const DEV_SHORTCUT_LOGIN_ENABLED = import.meta.env.VITE_ENABLE_DEV_SHORTCUT_LOGIN === 'true';
