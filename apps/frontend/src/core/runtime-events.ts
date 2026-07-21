import type { AssistantMode } from './assistant-modes';

export const AUTH_EXPIRED_EVENT = 'zhenhu:auth-expired';
export const NOTIFICATION_EVENT = 'zhenhu:notification';
export const OPEN_GLOBAL_ASSISTANT_EVENT = 'zhenhu:open-global-assistant';

export type NotificationDetail = { message: string; severity?: 'success' | 'info' | 'warning' | 'error' };

export function emitAuthExpired() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export function emitNotification(detail: NotificationDetail) {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent<NotificationDetail>(NOTIFICATION_EVENT, { detail }));
}

export interface OpenAssistantDetail {
  assistantMode?: AssistantMode;
}

export function emitOpenGlobalAssistant(assistantMode?: AssistantMode) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<OpenAssistantDetail>(OPEN_GLOBAL_ASSISTANT_EVENT, {
      detail: { assistantMode },
    }));
  }
}
