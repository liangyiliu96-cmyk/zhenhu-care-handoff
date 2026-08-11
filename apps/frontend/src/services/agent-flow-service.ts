import { apiGet } from '@/core/api-client';

export type AgentFlowMode = 'rule' | 'rag' | 'llm' | 'human' | 'record';
export type AgentFlowStatus = 'completed' | 'pending' | 'idle';
export interface AgentFlowStage { id: string; title: string; mode: AgentFlowMode; status: AgentFlowStatus; description: string; inputs?: string[]; outputs: string[]; }
export interface AgentArtifact { id: string; title: string; generator: 'rule' | 'llm'; status: string; citation_count: number; guardrail: string; }
export interface AgentCitation { title: string; source: string; excerpt: string; }
export interface AgentPendingReview { review_type: 'doctor_confirm' | 'med_confirm' | 'discharge_sign' | string; review_id: string; label: string; }
export interface AgentTurnJournalEntry { turn_id: string; occurred_at: string; entry_strategy: string; status: 'completed' | 'failed'; latency_ms: number; rag_hit_count: number; knowledge_gap: boolean; node_count: number; error_message: string; }
export interface AgentExecutionTrace { turn_id: string; occurred_at: string; entry_strategy: string; status: 'completed' | 'failed'; latency_ms: number; rag_hit_count: number; node_path: string[]; error_message: string; }
export interface AgentFlowResponse { patient_id: string; flow_status: 'ready' | 'waiting_review'; state_version: number; pending_review?: AgentPendingReview | null; stages: AgentFlowStage[]; generated_artifacts: AgentArtifact[]; citations: AgentCitation[]; turn_journal: AgentTurnJournalEntry[]; latest_execution?: AgentExecutionTrace | null; safety_boundary: string; }

export const fetchAgentFlow = (patientId: string) => apiGet<AgentFlowResponse>(`/inpatient/${encodeURIComponent(patientId)}/agent-flow`);

export function normalizeAgentFlow(flow: AgentFlowResponse): AgentFlowResponse {
  return {
    ...flow,
    stages: Array.isArray(flow.stages) ? flow.stages.map((stage) => ({ ...stage, inputs: Array.isArray(stage.inputs) ? stage.inputs : [] })) : [],
    generated_artifacts: Array.isArray(flow.generated_artifacts) ? flow.generated_artifacts : [],
    citations: Array.isArray(flow.citations) ? flow.citations : [],
    turn_journal: Array.isArray(flow.turn_journal) ? flow.turn_journal : [],
    latest_execution: flow.latest_execution && typeof flow.latest_execution === 'object'
      ? { ...flow.latest_execution, node_path: Array.isArray(flow.latest_execution.node_path) ? flow.latest_execution.node_path : [] }
      : null,
  };
}

export function agentFlowSummary(stages: readonly AgentFlowStage[]) {
  return {
    completed: stages.filter((stage) => stage.status === 'completed').length,
    total: stages.length,
    current: stages.find((stage) => stage.status === 'pending')
      ?? stages.find((stage) => stage.status === 'idle')
      ?? null,
  };
}

export function stageStatusLabel(status: AgentFlowStatus): string {
  return ({ completed: '已完成', pending: '当前等待', idle: '尚未开始' } as Record<AgentFlowStatus, string>)[status];
}

export function agentStrategyLabel(value: string): string {
  return ({
    daily_round: '日常查房回路',
    admission: '入院评估回路',
    monitoring: '住院监测回路',
    discharge: '出院准备回路',
    handoff: '交接协同回路',
    follow_up: '出院随访回路',
  } as Record<string, string>)[value] || value;
}

export function stageModeDescription(mode: AgentFlowMode): string {
  return ({
    rule: '依据病种模板和硬性安全规则评估，不产生医嘱。',
    rag: '检索版本化临床证据并保留引用，供医生核对适用范围。',
    llm: '基于当前患者事实和证据生成草稿，不直接写入正式记录。',
    human: '等待医生完成审核、修改或签署，未确认前流程不会写回。',
    record: '仅写回已经过人工确认的正式记录或协同任务。',
  } as Record<AgentFlowMode, string>)[mode];
}
