import type { UserIdentity } from '@/types/auth';

export type WorkspaceKind = 'doctor' | 'nurse' | 'management';

export interface WorkspaceWelcomeCopy {
  headline: string;
  detail: string;
}

export function workspaceWelcomeFor(user: Pick<UserIdentity, 'name' | 'role' | 'title' | 'department'>, workspace: WorkspaceKind): WorkspaceWelcomeCopy {
  const name = user.name || '同事';
  const identity = [user.department, user.title].filter(Boolean).join(' · ') || '当前工作区';

  if (workspace === 'doctor') return { headline: `${name}，欢迎开始本轮诊疗`, detail: `${identity} · 优先处理告警、待审核与查房处置` };
  if (workspace === 'nurse') return { headline: `${name}，欢迎开始本班护理`, detail: `${identity} · 先完成高优先级任务与逾期监测` };

  return {
    headline: user.role === 'nurse' ? `${name}，欢迎查看本班执行质量` : `${name}，欢迎查看科室运行情况`,
    detail: `${identity} · 聚焦闭环质量、风险信号与知识治理`,
  };
}
