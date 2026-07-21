import type { RouteIdentity } from './default-route';
import { adminRoute, departmentManagementRoute } from './routes';

export type AdminTabId = 'overview' | 'knowledge' | 'evidence_graph' | 'templates' | 'organization' | 'ward' | 'nursing' | 'handoff' | 'checklist' | 'integrations' | 'operations';

export interface AdminTab {
  id: AdminTabId;
  label: string;
  description: string;
  icon: string;
  path: string;
}

const DOCTOR_TABS: AdminTab[] = [
  { id: 'overview', label: '管理总览', description: '汇总病区负荷、风险处置、交接状态与团队运行情况，支持科主任快速判断本日管理重点。', icon: 'layout-dashboard', path: adminRoute('overview') },
  { id: 'evidence_graph', label: '证据图谱', description: '查看病种路径、证据来源、规则覆盖与图谱运行状态。', icon: 'network', path: adminRoute('evidence_graph') },
  { id: 'knowledge', label: '知识库治理', description: '检查临床知识完整度、检索条目并处理索引维护任务。', icon: 'book-open', path: adminRoute('knowledge') },
  { id: 'templates', label: '病种模板', description: '浏览已部署的病种模板及其适用科室，核对入院智能流程的配置范围。', icon: 'files', path: adminRoute('templates') },
  { id: 'organization', label: '组织架构', description: '查看科室、医生与护理人员配置及当前管理范围。', icon: 'users', path: adminRoute('organization') },
  { id: 'ward', label: '病区运营', description: '掌握在院负荷、高风险患者、待审核事项与全病区告警。', icon: 'bar-chart-2', path: adminRoute('ward') },
  { id: 'integrations', label: '集成状态', description: '核对临床决策支持服务发现、权限约束和端点状态。', icon: 'plug-zap', path: adminRoute('integrations') },
  { id: 'operations', label: '系统运维', description: '执行受审计保护的数据维护、种子、清理和索引操作。', icon: 'settings', path: adminRoute('operations') },
];

const NURSE_MANAGER_TABS: AdminTab[] = [
  { id: 'overview', label: '管理总览', description: '汇总班次执行、风险处置、交接状态和护理质量，支持护士长快速判断本日管理重点。', icon: 'layout-dashboard', path: adminRoute('overview') },
  { id: 'evidence_graph', label: '证据图谱', description: '查看护理规则、病种路径、证据来源与图谱运行状态。', icon: 'network', path: adminRoute('evidence_graph') },
  { id: 'nursing', label: '护理质控', description: '查看护理任务完成率、逾期情况、执行分类和最近完成记录。', icon: 'clipboard-check', path: adminRoute('nursing') },
  { id: 'handoff', label: '交班管理', description: '汇总重点患者、今日出院与稳定患者，核对智能交班摘要。', icon: 'git-compare', path: adminRoute('handoff') },
  { id: 'checklist', label: '制度执行质量', description: '查看制度要求对应的患者任务、执行留痕与质量趋势。', icon: 'list-checks', path: adminRoute('checklist') },
  { id: 'knowledge', label: '知识库治理', description: '与科主任共享临床知识库状态、检索和索引维护能力。', icon: 'book-open', path: adminRoute('knowledge') },
  { id: 'templates', label: '病种模板', description: '浏览已部署的病种模板及其适用科室，核对入院智能流程的配置范围。', icon: 'files', path: adminRoute('templates') },
  { id: 'organization', label: '组织架构', description: '查看医疗线与护理线的负责人、班组成员和当前管理范围。', icon: 'users', path: adminRoute('organization') },
  { id: 'integrations', label: '集成状态', description: '核对临床决策支持服务发现、权限约束和端点状态。', icon: 'plug-zap', path: adminRoute('integrations') },
  { id: 'operations', label: '系统运维', description: '执行受审计保护的数据维护、种子、清理和索引操作。', icon: 'settings', path: adminRoute('operations') },
];

export function adminTabsFor(user: RouteIdentity): AdminTab[] {
  const tabs = user.role === 'nurse' ? NURSE_MANAGER_TABS : DOCTOR_TABS;
  if (!user.department?.trim()) return tabs;
  return tabs.map((tab) => ({
    ...tab,
    path: departmentManagementRoute(user.department!, tab.id),
  }));
}
