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
export const OIDC_AUTHORITY = import.meta.env.VITE_OIDC_AUTHORITY || 'http://localhost:8080/realms/zhenhu';
export const OIDC_CLIENT_ID = import.meta.env.VITE_OIDC_CLIENT_ID || 'zhenhu-web';
export const OIDC_REDIRECT_URI = import.meta.env.VITE_OIDC_REDIRECT_URI || 'http://localhost:5173/callback';
export const DEV_SHORTCUT_LOGIN_ENABLED = import.meta.env.VITE_ENABLE_DEV_SHORTCUT_LOGIN === 'true';
