import { ApiClientError, apiGet, apiPatch, apiPost, resolveApiUrl } from '@/core/api-client';
import { API_TIMEOUT_AGENT } from '@/config/api';
import { getAuthHeaders } from '@/core/auth-bridge';
import type { AssistantMode } from '@/core/assistant-modes';

export interface AssistantCitation {
  source?: string;
  title?: string;
  content?: string;
  excerpt?: string;
  citation?: string;
  version?: string;
  [key: string]: unknown;
}

export interface AssistantEvidenceDiagnostics {
  status?: 'ok' | 'skipped' | 'no_evidence' | 'low_relevance' | 'version_mismatch' | 'lifecycle_mismatch' | 'graph_mismatch' | 'index_error' | string;
  policy_version?: string;
  accepted_count?: number;
  raw_count?: number;
  degraded?: boolean;
  [key: string]: unknown;
}

export interface AssistantQuickQuestions {
  role: string;
  assistant_mode?: AssistantMode;
  questions: string[];
}

export interface AssistantSessionSummary { session_id: string; assistant_mode: AssistantMode; patient_id: string; created_at?: number; updated_at?: number; message_count: number; }
export interface AssistantSessionDetail extends AssistantSessionSummary { history: Array<{ role: 'user' | 'assistant'; content: string; time?: number }>; }

export type AssistantActionDraftType = 'medication_order' | 'investigation_order' | 'follow_up_task' | 'mdt_request' | 'education_plan';
export type AssistantActionDraftStatus = 'pending' | 'approved' | 'rejected';

export interface AssistantActionDraft {
  id: string;
  draft_type: AssistantActionDraftType;
  status: AssistantActionDraftStatus;
  payload: Record<string, string | string[] | null | undefined>;
  rationale: string;
  citations: AssistantCitation[];
  session_id: string;
  source_message_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  decision_comment?: string;
  execution?: { record_type: AssistantActionDraftType; record_id: string; status: string } | null;
}

export interface AssistantActionDraftList {
  patient_id: string;
  state_version: number;
  drafts: AssistantActionDraft[];
}

export interface AssistantActionDraftMutation extends AssistantActionDraftList {
  draft?: AssistantActionDraft;
  execution?: { record_type: AssistantActionDraftType; record_id: string; status: string } | null;
  idempotent?: boolean;
}

export const fetchAssistantSessions = () => apiGet<{ sessions: AssistantSessionSummary[] }>('/assistant/sessions');
export const fetchAssistantSession = (sessionId: string) => apiGet<AssistantSessionDetail>(`/assistant/session/${encodeURIComponent(sessionId)}`);
export const resetAssistantSession = (sessionId: string) => apiPost<{ status: string }>(`/assistant/session/${encodeURIComponent(sessionId)}/reset`);
export const fetchAssistantActionDrafts = (patientId: string) => apiGet<AssistantActionDraftList>(`/inpatient/${encodeURIComponent(patientId)}/assistant-action-drafts`);
export const generateAssistantActionDrafts = (
  patientId: string,
  payload: { session_id: string; source_text: string; citations: AssistantCitation[]; expected_version: number },
) => apiPost<AssistantActionDraftMutation>(
  `/inpatient/${encodeURIComponent(patientId)}/assistant-action-drafts/generate`,
  payload,
  API_TIMEOUT_AGENT,
  { 'Idempotency-Key': operationKey('assistant-draft-generate') },
);
export const updateAssistantActionDraft = (
  patientId: string,
  draftId: string,
  payload: { payload: Record<string, string | string[] | null | undefined>; rationale: string; expected_version: number },
) => apiPatch<AssistantActionDraftMutation>(
  `/inpatient/${encodeURIComponent(patientId)}/assistant-action-drafts/${encodeURIComponent(draftId)}`,
  payload,
  { 'Idempotency-Key': operationKey('assistant-draft-update') },
);
export const decideAssistantActionDraft = (
  patientId: string,
  draftId: string,
  decision: 'approve' | 'reject',
  payload: { comment: string; expected_version: number },
) => apiPost<AssistantActionDraftMutation>(
  `/inpatient/${encodeURIComponent(patientId)}/assistant-action-drafts/${encodeURIComponent(draftId)}/${decision}`,
  payload,
  undefined,
  { 'Idempotency-Key': operationKey(`assistant-draft-${decision}`) },
);

export interface AssistantStreamRequest {
  message: string;
  assistantMode: AssistantMode;
  patientId?: string;
  sessionId?: string;
  publicAccess?: boolean;
}

export interface AssistantStreamPayload {
  token?: string;
  done?: boolean;
  session_id?: string;
  sources?: string[];
  citations?: AssistantCitation[];
  backend?: string;
  cache_hit?: boolean;
  intent?: { name?: string; label?: string; confidence?: number; layers?: string[] };
  evidence?: AssistantEvidenceDiagnostics;
}

export type AssistantStreamEvent =
  | { type: 'token'; token: string }
  | {
    type: 'complete';
    sessionId?: string;
    sources: string[];
    citations: AssistantCitation[];
    backend?: string;
    cacheHit?: boolean;
    intent?: { name?: string; label?: string; confidence?: number; layers?: string[] };
    evidence?: AssistantEvidenceDiagnostics;
  };

export function fetchAssistantQuickQuestions(
  assistantMode: AssistantMode,
  context: 'patient' | 'general' = 'patient',
  publicAccess = false,
): Promise<AssistantQuickQuestions> {
  if (publicAccess) return apiGet<AssistantQuickQuestions>('/assistant/public/quick-questions');
  return apiGet<AssistantQuickQuestions>(`/assistant/quick-questions?assistant_mode=${encodeURIComponent(assistantMode)}&context=${context}`);
}

export function parseAssistantSseFrames(buffer: string): {
  events: AssistantStreamPayload[];
  remainder: string;
} {
  const frames = buffer.split(/\r?\n\r?\n/);
  const remainder = frames.pop() ?? '';
  const events = frames.flatMap((frame) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) return [];
    try {
      const parsed = JSON.parse(data) as unknown;
      return parsed && typeof parsed === 'object' ? [parsed as AssistantStreamPayload] : [];
    } catch {
      return [];
    }
  });
  return { events, remainder };
}

export async function streamAssistantChat(
  request: AssistantStreamRequest,
  onEvent: (event: AssistantStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    const publicClientId = request.publicAccess ? getPublicAssistantClientId() : '';
    response = await fetch(resolveApiUrl(request.publicAccess ? '/assistant/public/chat/stream' : '/assistant/chat/stream'), {
      method: 'POST',
      headers: {
        ...(request.publicAccess ? { 'x-assistant-client': publicClientId } : getAuthHeaders()),
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        message: request.message,
        ...(!request.publicAccess ? {
          assistant_mode: request.assistantMode,
          patient_id: request.patientId ?? '',
        } : {}),
        ...(request.sessionId ? { session_id: request.sessionId } : {}),
      }),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiClientError(0, 'NETWORK_ERROR', '无法连接智能助手服务');
  }

  if (!response.ok) throw await toAssistantError(response);
  if (!response.body) throw new ApiClientError(0, 'STREAM_UNAVAILABLE', '智能助手未返回可读取的流');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const emit = (payload: AssistantStreamPayload) => {
    if (payload.token) onEvent({ type: 'token', token: payload.token });
    if (payload.done) {
      onEvent({
        type: 'complete',
        sessionId: payload.session_id,
        sources: payload.sources ?? [],
        citations: payload.citations ?? [],
        backend: payload.backend,
        cacheHit: payload.cache_hit,
        intent: payload.intent,
        evidence: payload.evidence,
      });
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (value) {
        const parsed = parseAssistantSseFrames(buffer + decoder.decode(value, { stream: true }));
        buffer = parsed.remainder;
        parsed.events.forEach(emit);
      }
      if (done) break;
    }
    const final = parseAssistantSseFrames(buffer + decoder.decode());
    final.events.forEach(emit);
  } finally {
    reader.releaseLock();
  }
}

async function toAssistantError(response: Response): Promise<ApiClientError> {
  const payload = await response.json().catch(() => ({})) as {
    detail?: string;
    error?: { code?: string; message?: string };
  };
  const message = payload.error?.message ?? payload.detail ?? `智能助手请求失败 (${response.status})`;
  if (response.status === 401) return new ApiClientError(401, 'UNAUTHORIZED', '会话已过期，请重新登录');
  if (response.status === 403) return new ApiClientError(403, 'FORBIDDEN', '无该患者的智能助手访问权限');
  if (response.status === 409) return new ApiClientError(409, 'ASSISTANT_SESSION_CONFLICT', message);
  if (response.status === 429) return new ApiClientError(429, 'ASSISTANT_RATE_LIMIT', '提问较频繁，请稍后再试');
  return new ApiClientError(response.status, payload.error?.code ?? 'ASSISTANT_ERROR', message);
}

function getPublicAssistantClientId(): string {
  const storageKey = 'zhenhu_public_assistant_client';
  const existing = sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const generated = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `public-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  sessionStorage.setItem(storageKey, generated);
  return generated;
}

function operationKey(prefix: string): string {
  const suffix = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  return `${prefix}-${suffix}`;
}
