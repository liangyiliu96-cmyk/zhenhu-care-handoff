// 共享临床契约：病例、知识、入库任务状态机与最小角色访问边界。
// 该包是正式项目与 PoC 共同引用的唯一状态机事实来源，不允许在调用方各自硬编码状态转移。
// 状态定义对照《需求规格说明书 v0.2》§3.4（病例状态机）与 §4.4（知识版本状态）。

const caseTransitions = new Map([
  ["draft", new Set(["analysing", "cancelled"])],
  ["analysing", new Set(["review_pending", "failed", "cancelled"])],
  ["review_pending", new Set(["confirmed", "rejected", "task_draft", "cancelled", "knowledge_changed"])],
  ["confirmed", new Set(["task_draft", "cancelled"])],
  ["rejected", new Set(["task_draft", "cancelled"])],
  ["task_draft", new Set(["simulated_published", "review_pending", "cancelled", "knowledge_changed"])],
  ["simulated_published", new Set(["closed", "cancelled"])],
  ["knowledge_changed", new Set(["review_pending", "cancelled"])],
  ["failed", new Set(["analysing"])],
  ["cancelled", new Set()],
  ["closed", new Set()]
]);

const knowledgeTransitions = new Map([
  ["review_pending", new Set(["published", "withdrawn", "review_rejected"])],
  ["published", new Set(["expired", "withdrawn", "superseded", "archived"])],
  ["expired", new Set()],
  ["withdrawn", new Set()],
  ["superseded", new Set()],
  ["archived", new Set()],
  ["review_rejected", new Set()]
]);

const ingestionJobTransitions = new Map([
  ["queued", new Set(["parsing"])],
  ["parsing", new Set(["review_pending", "failed"])],
  ["review_pending", new Set()],
  ["failed", new Set(["queued"])]
]);

export const CASE_STATES = Object.freeze([...caseTransitions.keys()]);
export const KNOWLEDGE_DOCUMENT_STATES = Object.freeze([...knowledgeTransitions.keys()]);
export const KNOWLEDGE_INGESTION_JOB_STATES = Object.freeze([...ingestionJobTransitions.keys()]);

// knowledge_changed 仅作为在办病例的阻断态：当其所引用的已发布知识过期/撤回/被替代时进入，
// 须由医生重新检索与人工复核后才能回到 review_pending。见需求 §4.4 末段。
export const CASE_BLOCKING_STATES = Object.freeze(["knowledge_changed", "failed", "cancelled", "closed"]);

export const CLINICAL_ROLES = Object.freeze(["doctor", "nurse", "case_manager", "auditor", "knowledge_admin"]);

export const SURFACE_PERMISSIONS = Object.freeze({
  case_review: Object.freeze(["doctor", "auditor"]),
  simulated_tasks: Object.freeze(["doctor", "nurse", "case_manager"]),
  knowledge_documents: Object.freeze(["doctor", "auditor", "knowledge_admin"]),
  knowledge_import: Object.freeze(["knowledge_admin"]),
  knowledge_runtime_reset: Object.freeze(["knowledge_admin"])
});

export function isAllowedTransition(graph, currentState, nextState) {
  return graph.get(currentState)?.has(nextState) ?? false;
}

export function assertCaseTransition(currentState, nextState) {
  if (!caseTransitions.has(currentState)) {
    throw new Error(`Unknown case state: ${currentState}`);
  }
  if (!isAllowedTransition(caseTransitions, currentState, nextState)) {
    throw new Error(`Illegal case transition: ${currentState} -> ${nextState}`);
  }
  return true;
}

export function assertKnowledgeTransition(currentState, nextState) {
  if (!knowledgeTransitions.has(currentState)) {
    throw new Error(`Unknown knowledge state: ${currentState}`);
  }
  if (!isAllowedTransition(knowledgeTransitions, currentState, nextState)) {
    throw new Error(`Illegal knowledge transition: ${currentState} -> ${nextState}`);
  }
  return true;
}

export function assertIngestionJobTransition(currentState, nextState) {
  if (!ingestionJobTransitions.has(currentState)) {
    throw new Error(`Unknown ingestion job state: ${currentState}`);
  }
  if (!isAllowedTransition(ingestionJobTransitions, currentState, nextState)) {
    throw new Error(`Illegal ingestion job transition: ${currentState} -> ${nextState}`);
  }
  return true;
}

export function canRoleAccessSurface(role, surface) {
  return SURFACE_PERMISSIONS[surface]?.includes(role) ?? false;
}

export function assertRoleAccess(role, surface) {
  if (!CLINICAL_ROLES.includes(role)) {
    throw new Error(`Unknown role: ${role}`);
  }
  if (!canRoleAccessSurface(role, surface)) {
    throw new Error(`Role ${role} cannot access ${surface}`);
  }
  return true;
}

export function buildContractSnapshot() {
  return {
    caseStates: CASE_STATES,
    knowledgeStates: KNOWLEDGE_DOCUMENT_STATES,
    ingestionJobStates: KNOWLEDGE_INGESTION_JOB_STATES,
    blockingCaseStates: CASE_BLOCKING_STATES,
    surfaces: Object.keys(SURFACE_PERMISSIONS)
  };
}
