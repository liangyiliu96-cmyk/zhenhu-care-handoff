import { apiGet } from '@/core/api-client';

export type AgentFlowMode = 'rule' | 'rag' | 'llm' | 'human' | 'record';
export type AgentFlowStatus = 'completed' | 'pending' | 'idle';
export interface AgentFlowStage { id: string; title: string; mode: AgentFlowMode; status: AgentFlowStatus; description: string; outputs: string[]; }
export interface AgentArtifact { id: string; title: string; generator: 'rule' | 'llm'; status: string; citation_count: number; guardrail: string; }
export interface AgentCitation { title: string; source: string; excerpt: string; }
export interface AgentPendingReview { review_type: 'doctor_confirm' | 'med_confirm' | 'discharge_sign' | string; review_id: string; label: string; }
export interface AgentTurnJournalEntry { turn_id: string; occurred_at: string; entry_strategy: string; status: 'completed' | 'failed'; latency_ms: number; rag_hit_count: number; knowledge_gap: boolean; node_count: number; error_message: string; }
export interface AgentFlowResponse { patient_id: string; flow_status: 'ready' | 'waiting_review'; state_version: number; pending_review?: AgentPendingReview | null; stages: AgentFlowStage[]; generated_artifacts: AgentArtifact[]; citations: AgentCitation[]; turn_journal: AgentTurnJournalEntry[]; safety_boundary: string; }

export const fetchAgentFlow = (patientId: string) => apiGet<AgentFlowResponse>(`/inpatient/${encodeURIComponent(patientId)}/agent-flow`);

export function normalizeAgentFlow(flow: AgentFlowResponse): AgentFlowResponse {
  return {
    ...flow,
    stages: Array.isArray(flow.stages) ? flow.stages : [],
    generated_artifacts: Array.isArray(flow.generated_artifacts) ? flow.generated_artifacts : [],
    citations: Array.isArray(flow.citations) ? flow.citations : [],
    turn_journal: Array.isArray(flow.turn_journal) ? flow.turn_journal : [],
  };
}
