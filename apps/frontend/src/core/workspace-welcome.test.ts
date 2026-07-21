import { describe, expect, it } from 'vitest';

import { workspaceWelcomeFor } from './workspace-welcome';

const doctor = { name: '张医生', role: 'doctor' as const, title: '主治医师', department: '心内科' };

describe('workspaceWelcomeFor', () => {
  it('gives doctors a clinically focused welcome', () => {
    expect(workspaceWelcomeFor(doctor, 'doctor')).toEqual({
      headline: '张医生，欢迎开始本轮诊疗',
      detail: '心内科 · 主治医师 · 优先处理告警、待审核与查房处置',
    });
  });

  it('uses the nursing quality context in the management workspace', () => {
    const copy = workspaceWelcomeFor({ name: '王护士长', role: 'nurse', title: '护士长', department: '呼吸科' }, 'management');
    expect(copy.headline).toBe('王护士长，欢迎查看本班执行质量');
    expect(copy.detail).toContain('呼吸科 · 护士长');
  });
});
