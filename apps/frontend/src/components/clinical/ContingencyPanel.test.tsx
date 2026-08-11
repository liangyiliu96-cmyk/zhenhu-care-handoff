// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import ContingencyPanel from './ContingencyPanel';

afterEach(cleanup);

describe('ContingencyPanel', () => {
  it('turns high-risk structured scores into an actionable warning', () => {
    render(
      <ContingencyPanel
        dashboard={{ phase: 'monitoring', vital_trend: [] } as never}
        scores={{
          patient_id: 'patient-1',
          news2: { score: 7, risk: 'high', status: 'available' },
          qsofa: { score: 0, risk: 'low', status: 'available' },
          padua: { score: 2, risk: 'low', status: 'available' },
          vte_prophylaxis: 'pending',
          stroke_antithrombotic: 'not_applicable',
          mdt: 'not triggered',
        }}
      />,
    );

    expect(screen.getByText(/NEWS2=7/)).toBeTruthy();
    expect(screen.getByText(/持续监测生命体征/)).toBeTruthy();
    expect(screen.getByText('应急关注')).toBeTruthy();
  });
});
