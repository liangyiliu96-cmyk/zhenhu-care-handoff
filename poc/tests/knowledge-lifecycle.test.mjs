import assert from "node:assert/strict";
import test from "node:test";
import { KnowledgeRegistry } from "../api/knowledge.mjs";
import { PocWorkflow, WorkflowError } from "../api/workflow.mjs";

const createKnowledge = (options = {}) => new KnowledgeRegistry({ persistRuntime: false, ...options });

const textSource = (input) => ({ sourceMime: input.sourceFormat === "md" ? "text/markdown" : "text/plain", ...input });

test("知识管理员可将已发布文档标记为 superseded 或 archived（均为终止态）", async () => {
  const knowledge = createKnowledge();
  const supersedeDoc = await knowledge.import("knowledge_admin", textSource({
    title: "可被替代的文档", version: "0.1", owner: "药学部（模拟）", sourceFileName: "supersede.md", sourceFormat: "md",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "该模拟文档用于验证已发布版本可被标记为替代或归档。"
  }));
  const published = knowledge.transition("knowledge_admin", supersedeDoc.documentId, "published");
  assert.equal(published.status, "published");
  const superseded = knowledge.transition("knowledge_admin", supersedeDoc.documentId, "superseded");
  assert.equal(superseded.status, "superseded");
  const afterSupersede = await knowledge.search("doctor", "可被标记为替代或归档");
  assert.ok(!afterSupersede.some((result) => result.documentId === supersedeDoc.documentId), "被替代文档不应再被检索到");

  const archiveDoc = await knowledge.import("knowledge_admin", textSource({
    title: "可被归档的文档", version: "0.1", owner: "药学部（模拟）", sourceFileName: "archive.md", sourceFormat: "md",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "该模拟文档用于验证已发布版本可被归档并停止参与检索。"
  }));
  knowledge.transition("knowledge_admin", archiveDoc.documentId, "published");
  const archived = knowledge.transition("knowledge_admin", archiveDoc.documentId, "archived");
  assert.equal(archived.status, "archived");
});

test("待审核文档可被审核驳回为 review_rejected 且不可再发布", async () => {
  const knowledge = createKnowledge();
  const imported = await knowledge.import("knowledge_admin", textSource({
    title: "待驳回文档", version: "0.1", owner: "护理部（模拟）", sourceFileName: "reject.md", sourceFormat: "md",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "该模拟文档用于验证待审核文档可被审核驳回。"
  }));
  const rejected = knowledge.transition("knowledge_admin", imported.documentId, "review_rejected");
  assert.equal(rejected.status, "review_rejected");
  assert.throws(() => knowledge.transition("knowledge_admin", imported.documentId, "published"), (error) => error instanceof WorkflowError && error.code === "KNOWLEDGE_STATE_CONFLICT");
});

test("引用过期知识时在办病例被反向阻断（服务端钩子集成）", async () => {
  const knowledge = createKnowledge();
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  for (const risk of workflow.overview("doctor").risks) workflow.reviewRisk("doctor", risk.riskId, "confirm");
  workflow.createTaskDraft("doctor");
  const updated = knowledge.transition("knowledge_admin", "poc-followup-sop", "expired");
  if (["expired", "withdrawn", "superseded"].includes(updated.status)) workflow.onKnowledgeUnavailable(updated.documentId, "knowledge_admin");
  assert.equal(workflow.overview("doctor").case.state, "knowledge_changed");
});
