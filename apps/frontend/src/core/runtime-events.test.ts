// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { AUTH_EXPIRED_EVENT, NOTIFICATION_EVENT, OPEN_GLOBAL_ASSISTANT_EVENT, emitAuthExpired, emitNotification, emitOpenGlobalAssistant } from './runtime-events';

describe('runtime events', () => {
  it('publishes auth expiry and notification events without coupling the API client to routing', () => {
    const expired = vi.fn();
    const notification = vi.fn();
    const assistant = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired, { once: true });
    window.addEventListener(NOTIFICATION_EVENT, notification, { once: true });
    window.addEventListener(OPEN_GLOBAL_ASSISTANT_EVENT, assistant, { once: true });
    emitAuthExpired();
    emitNotification({ severity: 'warning', message: '会话已过期' });
    emitOpenGlobalAssistant('pharmacist');
    expect(expired).toHaveBeenCalledOnce();
    expect(notification).toHaveBeenCalledOnce();
    expect(assistant).toHaveBeenCalledOnce();
    expect((assistant.mock.calls[0][0] as CustomEvent).detail).toEqual({ assistantMode: 'pharmacist' });
  });
});
