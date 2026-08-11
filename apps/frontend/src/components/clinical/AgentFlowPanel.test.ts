import { describe, expect, it } from 'vitest';

import { agentFlowSummary, agentStrategyLabel, normalizeAgentFlow, stageModeDescription, stageStatusLabel } from '@/services/agent-flow-service';
import type { AgentFlowResponse, AgentFlowStage } from '@/services/agent-flow-service';

describe('normalizeAgentFlow', () => {
  it('keeps the patient workspace renderable when an optional flow projection is absent', () => {
    const flow = normalizeAgentFlow({
      patient_id: 'patient-1',
      flow_status: 'ready',
      state_version: 3,
      safety_boundary: 'human confirmation required',
      stages: undefined,
      generated_artifacts: undefined,
      citations: undefined,
      turn_journal: undefined,
    } as unknown as AgentFlowResponse);

    expect(flow.stages).toEqual([]);
    expect(flow.generated_artifacts).toEqual([]);
    expect(flow.citations).toEqual([]);
    expect(flow.turn_journal).toEqual([]);
  });

  it('projects the current clinical node and localizes internal execution labels', () => {
    const stages: AgentFlowStage[] = [
      { id: 'collect', title: '临床数据采集', mode: 'rule', status: 'completed', description: '', outputs: [] },
      { id: 'evidence', title: '知识检索与证据', mode: 'rag', status: 'pending', description: '', outputs: [] },
      { id: 'reason', title: '规则与 LLM 推理', mode: 'llm', status: 'idle', description: '', outputs: [] },
    ];

    expect(agentFlowSummary(stages)).toEqual({ completed: 1, total: 3, current: stages[1] });
    expect(stageStatusLabel('pending')).toBe('当前等待');
    expect(agentStrategyLabel('daily_round')).toBe('日常查房回路');
    expect(stageModeDescription('llm')).toContain('不直接写入正式记录');
    expect(agentStrategyLabel('unknown_strategy')).toBe('unknown_strategy');
  });
});
