import assert from "node:assert/strict";
import test from "node:test";
import { PocWorkflow, WorkflowError } from "../api/workflow.mjs";
import { KnowledgeRegistry } from "../api/knowledge.mjs";

const createKnowledge = (options = {}) => new KnowledgeRegistry({ persistRuntime: false, ...options });

const confirmAll = (workflow) => {
  for (const risk of workflow.overview("doctor").risks) workflow.reviewRisk("doctor", risk.riskId, "confirm");
};

test("全部确认后病例进入 confirmed 状态再生成任务草稿", () => {
  const workflow = new PocWorkflow();
  confirmAll(workflow);
  assert.equal(workflow.overview("doctor").case.state, "confirmed");
  const drafted = workflow.createTaskDraft("doctor");
  assert.equal(drafted.case.state, "task_draft");
  assert.equal(drafted.taskDraft.basedOnRiskIds.length, 4);
});

test("存在驳回时病例进入 rejected 状态但仍可生成草稿", () => {
  const workflow = new PocWorkflow();
  workflow.reviewRisk("doctor", "risk-allergy-01", "confirm");
  workflow.reviewRisk("doctor", "risk-renal-01", "reject");
  workflow.reviewRisk("doctor", "risk-bp-01", "confirm");
  workflow.reviewRisk("doctor", "risk-dose-01", "confirm");
  assert.equal(workflow.overview("doctor").case.state, "rejected");
  const drafted = workflow.createTaskDraft("doctor");
  assert.equal(drafted.case.state, "task_draft");
  assert.equal(drafted.taskDraft.basedOnRiskIds.length, 3);
});

test("已模拟发布病例可被医生关闭", () => {
  const workflow = new PocWorkflow();
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  workflow.publish("doctor");
  const closed = workflow.close("doctor");
  assert.equal(closed.case.state, "closed");
});

test("非终态病例可被医生取消", () => {
  const workflow = new PocWorkflow();
  const cancelled = workflow.cancel("doctor");
  assert.equal(cancelled.case.state, "cancelled");
});

test("已发布知识过期/撤回后在办病例被标记为 knowledge_changed 并阻断发布", () => {
  const knowledge = createKnowledge();
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  // 模拟服务端在知识过期后触发的在办病例阻断
  knowledge.transition("knowledge_admin", "poc-followup-sop", "expired");
  workflow.onKnowledgeUnavailable("poc-followup-sop");
  assert.equal(workflow.overview("doctor").case.state, "knowledge_changed");
  assert.throws(() => workflow.publish("doctor"), (error) => error instanceof WorkflowError && error.code === "KNOWLEDGE_CHANGED");
});

test("knowledge_changed 病例可重新核实回到可审核态", () => {
  const knowledge = createKnowledge();
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  // 模拟所引用知识变化触发阻断（知识在重核时已恢复可用）
  workflow.onKnowledgeUnavailable("poc-followup-sop", "knowledge_admin");
  const reconciled = workflow.reconcile("doctor");
  assert.equal(reconciled.case.state, "review_pending");
  assert.equal(reconciled.risks.length, 4);
  assert.equal(reconciled.taskDraft, null);
});

test("护士可为指派给本人的任务补充执行信息", () => {
  const workflow = new PocWorkflow();
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  workflow.publish("doctor");
  const supplemented = workflow.supplementTask("nurse", "task-01", { result: "已核对用药与过敏史", note: "记录一致" });
  const task = supplemented.tasks.find((task) => task.taskId === "task-01");
  assert.equal(task.status, "simulated_supplemented");
  assert.ok(task.executionResult?.result);
  assert.equal(task.executionResult.actor, "nurse");
});

test("护士不能补充非指派给本人的任务", () => {
  const workflow = new PocWorkflow();
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  workflow.publish("doctor");
  assert.throws(() => workflow.supplementTask("nurse", "task-02", {}), (error) => error instanceof WorkflowError && error.code === "ACCESS_DENIED");
});

test("引用无关知识变化的在办病例不被阻断", () => {
  const knowledge = createKnowledge();
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  confirmAll(workflow);
  workflow.createTaskDraft("doctor");
  // 过期一份未被本病例引用的知识（drug-label 被引用，poc-handoff-sop 仅在冲突场景引用）
  knowledge.transition("knowledge_admin", "poc-handoff-sop", "expired");
  const flagged = workflow.onKnowledgeUnavailable("poc-handoff-sop");
  assert.equal(flagged, false);
  assert.equal(workflow.overview("doctor").case.state, "task_draft");
});

test("escalate 风险项后不阻止草稿生成", () => {
  const workflow = new PocWorkflow();
  // 确认 3 个基础风险项，第 4 个（dose）escalate
  workflow.reviewRisk("doctor", "risk-allergy-01", "confirm");
  workflow.reviewRisk("doctor", "risk-renal-01", "confirm");
  workflow.reviewRisk("doctor", "risk-bp-01", "confirm");
  workflow.reviewRisk("doctor", "risk-dose-01", "escalate", "", "需 MDT 讨论");
  const overview = workflow.overview("doctor");
  assert.equal(overview.case.state, "confirmed");
  const drafted = workflow.createTaskDraft("doctor");
  assert.equal(drafted.case.state, "task_draft");
  // basedOnRiskIds 不应包含 escalated 项
  assert.ok(!drafted.taskDraft.basedOnRiskIds.includes("risk-dose-01"));
  assert.equal(drafted.taskDraft.basedOnRiskIds.length, 3);
});

test("escalate 后 escalated 项不计入 confirmed", () => {
  const workflow = new PocWorkflow();
  // 确认 3 个风险，第 4 个 escalate
  workflow.reviewRisk("doctor", "risk-allergy-01", "confirm");
  workflow.reviewRisk("doctor", "risk-renal-01", "confirm");
  workflow.reviewRisk("doctor", "risk-bp-01", "confirm");
  workflow.reviewRisk("doctor", "risk-dose-01", "escalate", "", "需上级复核");
  // 状态转移应触发（因为没有 pending 项了，escalated 不计入 pending）
  const overview = workflow.overview("doctor");
  assert.equal(overview.case.state, "confirmed");
  // escalated 项状态确认
  const escalated = overview.risks.find((r) => r.riskId === "risk-dose-01");
  assert.equal(escalated.status, "escalated");
  assert.equal(escalated.decision.action, "escalate");
});

test("dischargeTo=\"居家\" 时 medium 风险升级为 high", () => {
  const workflow = new PocWorkflow();
  const overview = workflow.overview("doctor");
  // 默认场景 dischargeTo 为 "居家"
  assert.equal(overview.snapshot.patient.dischargeTo, "居家");
  // risk-renal-01 原始 severity 为 medium，应被升级为 high
  const renal = overview.risks.find((r) => r.riskId === "risk-renal-01");
  assert.equal(renal.severity, "high");
  assert.ok(renal.severityLabel.includes("居家升级"));
  assert.equal(renal.severityClass, "high");
  // risk-dose-01 原始 severity 为 medium，也应被升级
  const dose = overview.risks.find((r) => r.riskId === "risk-dose-01");
  assert.equal(dose.severity, "high");
  assert.ok(dose.severityLabel.includes("居家升级"));
});

test("data_conflict 场景含 5 个风险项", () => {
  const workflow = new PocWorkflow();
  workflow.reset("doctor");
  workflow.runAnalysis("doctor", { dataConflict: true });
  const overview = workflow.overview("doctor");
  // 4 基础风险项 + 1 冲突风险项 = 5
  assert.equal(overview.risks.length, 5);
  const conflict = overview.risks.find((r) => r.riskId === "risk-allergy-conflict-01");
  assert.ok(conflict);
  assert.equal(conflict.category, "source_conflict");
});

test("所有风险项 evidence 含 source_type 字段", () => {
  const workflow = new PocWorkflow();
  const overview = workflow.overview("doctor");
  const validTypes = ["source_ehr", "source_knowledge", "source_hybrid"];
  assert.equal(overview.risks.length, 4);
  for (const risk of overview.risks) {
    assert.ok(risk.evidence.source_type, `风险项 ${risk.riskId} 缺少 source_type`);
    assert.ok(validTypes.includes(risk.evidence.source_type), `风险项 ${risk.riskId} source_type 值不合法: ${risk.evidence.source_type}`);
  }
});
