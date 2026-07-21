import { describe, expect, it } from 'vitest';

import { parseAssistantSseFrames } from './assistant-service';

describe('parseAssistantSseFrames', () => {
  it('keeps an incomplete frame buffered and parses partial and terminal events', () => {
    const first = parseAssistantSseFrames('data: {"token":"建议","done":false}\n\ndata: {"token":"继续"');
    expect(first.events).toEqual([{ token: '建议', done: false }]);
    expect(first.remainder).toBe('data: {"token":"继续"');

    const second = parseAssistantSseFrames(`${first.remainder},"done":false}\n\ndata: {"token":"","done":true,"session_id":"session-1","sources":["指南"],"citations":[{"title":"指南","excerpt":"片段"}]}\n\n`);
    expect(second.remainder).toBe('');
    expect(second.events).toEqual([
      { token: '继续', done: false },
      { token: '', done: true, session_id: 'session-1', sources: ['指南'], citations: [{ title: '指南', excerpt: '片段' }] },
    ]);
  });

  it('ignores non-data and malformed frames', () => {
    const parsed = parseAssistantSseFrames(': heartbeat\n\ndata: invalid\n\n');
    expect(parsed.events).toEqual([]);
    expect(parsed.remainder).toBe('');
  });
});
