// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import PreRoundBriefPanel from './PreRoundBriefPanel';

const brief = {
  patient_id: 'patient-1',
  state_version: 7,
  attention_items: [{
    kind: 'clinical_alert',
    priority: 'high',
    title: '心率增快，需要复核',
    action: '请结合当前患者情况复核该告警。',
    facts: [{ source_type: 'clinical_alert', source_id: 'alert-1', observed_at: '2026-07-22T08:00:00Z', field: 'message', value: '心率增快，需要复核' }],
  }],
  history_gaps: [{ field: 'allergies', label: '过敏史', status: 'needs_input', prompt: '请补充过敏史。' }],
};

afterEach(cleanup);

describe('PreRoundBriefPanel', () => {
  it('shows sourced attention items and never presents history gaps as facts', () => {
    render(<PreRoundBriefPanel brief={brief} onGenerateDraft={vi.fn()} />);

    expect(screen.getByText('查房前预读')).toBeTruthy();
    expect(screen.getByText('心率增快，需要复核')).toBeTruthy();
    expect(screen.getByText('来源：clinical_alert')).toBeTruthy();
    expect(screen.getByText('待补：过敏史')).toBeTruthy();
    expect(screen.queryByText('过敏史已确认')).toBeNull();
  });

  it('requires an explicit click to request a progress note draft', () => {
    const onGenerateDraft = vi.fn();
    render(<PreRoundBriefPanel brief={brief} onGenerateDraft={onGenerateDraft} />);

    fireEvent.click(screen.getByRole('button', { name: '生成增量病程草稿' }));

    expect(onGenerateDraft).toHaveBeenCalledTimes(1);
  });
});
