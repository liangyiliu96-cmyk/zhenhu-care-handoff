import assert from "node:assert/strict";
import test from "node:test";
import {
  CASE_STATES,
  KNOWLEDGE_DOCUMENT_STATES,
  KNOWLEDGE_INGESTION_JOB_STATES,
  assertCaseTransition,
  assertKnowledgeTransition,
  assertIngestionJobTransition,
  assertRoleAccess,
  buildContractSnapshot
} from "../../packages/clinical-contracts/src/index.mjs";

test("共享契约包暴露正式项目需要的基础状态枚举", () => {
  assert.ok(CASE_STATES.includes("review_pending"));
  assert.ok(KNOWLEDGE_DOCUMENT_STATES.includes("published"));
  assert.ok(KNOWLEDGE_INGESTION_JOB_STATES.includes("failed"));
});

test("病例和知识状态机只允许已验证转移", () => {
  assert.equal(assertCaseTransition("review_pending", "task_draft"), true);
  assert.throws(() => assertCaseTransition("draft", "task_draft"));
  assert.equal(assertKnowledgeTransition("review_pending", "published"), true);
  assert.throws(() => assertKnowledgeTransition("published", "review_pending"));
  assert.equal(assertIngestionJobTransition("failed", "queued"), true);
  assert.throws(() => assertIngestionJobTransition("queued", "failed"));
});

test("共享契约包可裁决正式服务的最小角色访问边界", () => {
  assert.equal(assertRoleAccess("knowledge_admin", "knowledge_import"), true);
  assert.equal(assertRoleAccess("doctor", "knowledge_documents"), true);
  assert.throws(() => assertRoleAccess("nurse", "knowledge_import"));
});

test("共享契约快照可作为正式项目启动期自检输入", () => {
  const snapshot = buildContractSnapshot();
  assert.ok(snapshot.caseStates.length > 0);
  assert.ok(snapshot.surfaces.includes("knowledge_runtime_reset"));
});
