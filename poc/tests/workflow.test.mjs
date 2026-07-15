import assert from "node:assert/strict";
import test from "node:test";
import { PocWorkflow, WorkflowError } from "../api/workflow.mjs";

const expectError = (run, code) => {
  assert.throws(run, (error) => error instanceof WorkflowError && error.code === code);
};

test("护士无权审核风险项", () => {
  const workflow = new PocWorkflow();
  expectError(() => workflow.reviewRisk("nurse", "risk-allergy-01", "confirm"), "ACCESS_DENIED");
});

test("未知角色不能读取病例工作流", () => {
  const workflow = new PocWorkflow();
  expectError(() => workflow.overview("guest"), "ACCESS_DENIED");
});

test("护理角色在医生发布前不获取审核风险或审计记录", () => {
  const workflow = new PocWorkflow();
  const overview = workflow.overview("nurse");
  assert.equal(overview.risks.length, 0);
  assert.equal(overview.audit.length, 0);
  assert.equal(overview.taskDraft, null);
});

test("存在待审核风险项时不能生成任务草稿", () => {
  const workflow = new PocWorkflow();
  expectError(() => workflow.createTaskDraft("doctor"), "CASE_STATE_CONFLICT");
});

test("全部审核后生成草稿并模拟发布到待办", () => {
  const workflow = new PocWorkflow();
  workflow.reviewRisk("doctor", "risk-allergy-01", "confirm");
  workflow.reviewRisk("doctor", "risk-renal-01", "edit_confirm", "已人工核实");
  workflow.reviewRisk("doctor", "risk-bp-01", "reject");
  workflow.reviewRisk("doctor", "risk-dose-01", "confirm");
  const drafted = workflow.createTaskDraft("doctor");
  assert.equal(drafted.case.state, "task_draft");
  const published = workflow.publish("doctor");
  assert.equal(published.case.state, "simulated_published");
  assert.equal(published.tasks.length, 2);
  assert.ok(published.audit.some((event) => event.eventType === "simulated_publish"));
});

test("模拟检索依赖失败时不生成风险项或任务草稿", () => {
  const workflow = new PocWorkflow();
  workflow.reset("doctor");
  expectError(() => workflow.runAnalysis("doctor", { dependencyFailure: true }), "DEPENDENCY_UNAVAILABLE");
  const overview = workflow.overview("doctor");
  assert.equal(overview.case.state, "failed");
  assert.equal(overview.risks.length, 0);
  assert.equal(overview.taskDraft, null);
});

test("知识版本过期时进入失败状态且不返回风险项", () => {
  const workflow = new PocWorkflow();
  workflow.reset("doctor");
  expectError(() => workflow.runAnalysis("doctor", { knowledgeExpired: true }), "INSUFFICIENT_EVIDENCE");
  const overview = workflow.overview("doctor");
  assert.equal(overview.case.state, "failed");
  assert.equal(overview.risks.length, 0);
});

test("输入来源冲突必须并列成为待审核项", () => {
  const workflow = new PocWorkflow();
  workflow.reset("doctor");
  workflow.runAnalysis("doctor", { dataConflict: true });
  const conflict = workflow.overview("doctor").risks.find((risk) => risk.category === "source_conflict");
  assert.equal(conflict.status, "pending");
  assert.match(conflict.evidence.snippet, /来源 A/);
  assert.match(conflict.evidence.snippet, /来源 B/);
});

test("模拟发布不能重复执行", () => {
  const workflow = new PocWorkflow();
  for (const risk of workflow.overview("doctor").risks) workflow.reviewRisk("doctor", risk.riskId, "confirm");
  workflow.createTaskDraft("doctor");
  workflow.publish("doctor");
  expectError(() => workflow.publish("doctor"), "CASE_STATE_CONFLICT");
});
