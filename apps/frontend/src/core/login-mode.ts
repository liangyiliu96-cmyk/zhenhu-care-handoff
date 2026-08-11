export type LoginMode = 'header' | 'jwt' | 'oidc';

export function normalizeLoginMode(value: string): LoginMode {
  if (value === 'jwt' || value === 'oidc') return value;
  return 'header';
}

export function supportsCredentialLogin(mode: LoginMode): boolean {
  return mode === 'header' || mode === 'jwt';
}

/** 是否为 SSO 模式 (跳转医院统一认证, 不支持本地凭证表单)。 */
export function isSsoMode(mode: LoginMode): boolean {
  return mode === 'oidc';
}

export function loginModeDescription(mode: LoginMode): string {
  switch (mode) {
    case 'jwt':
      return '使用工号和密码登录，访问令牌仅保存在当前浏览器会话中。';
    case 'oidc':
      return '将跳转至医院统一身份认证服务完成登录。';
    default:
      return '当前为开发联调模式，可使用工号密码或开发身份进入系统。';
  }
}
