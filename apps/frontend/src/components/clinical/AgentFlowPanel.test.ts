import { describe, expect, it } from 'vitest';

import { normalizeAgentFlow } from '@/services/agent-flow-service';
import type { AgentFlowResponse } from '@/services/agent-flow-service';

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
});
