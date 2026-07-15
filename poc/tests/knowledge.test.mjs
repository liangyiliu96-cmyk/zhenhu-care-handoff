import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { KnowledgeRegistry } from "../api/knowledge.mjs";
import { PocWorkflow, WorkflowError } from "../api/workflow.mjs";
import { DocumentParseError, parseKnowledgeSource } from "../api/document-parser.mjs";

const textSource = (input) => ({ sourceMime: input.sourceFormat === "md" ? "text/markdown" : "text/plain", ...input });

async function completedJob(knowledge, jobId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const job = knowledge.getImportJob("knowledge_admin", jobId);
    if (["review_pending", "failed"].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error(`Timed out waiting for knowledge ingestion job ${jobId}`);
}

function createRuntimeStatePath() {
  const directory = mkdtempSync(join(tmpdir(), "zhenhu-knowledge-"));
  return {
    runtimeStatePath: join(directory, "knowledge-state.json"),
    cleanup() {
      rmSync(directory, { recursive: true, force: true });
    }
  };
}

function createKnowledge(options = {}) {
  return new KnowledgeRegistry({ persistRuntime: false, ...options });
}

test("仅已发布且有效的知识文档参与词法检索", async () => {
  const knowledge = createKnowledge();
  const results = await knowledge.search("doctor", "青霉素 过敏");
  assert.equal(results.length, 1);
  assert.equal(results[0].documentId, "drug-label-amoxicillin-clavulanate");
  assert.equal(results[0].status, "published");
  assert.equal(results[0].retrievalStrategyVersion, "poc-hybrid-tfidf-rag-0.1");
  assert.ok(results[0].score > 0);
});

test("中文连续查询在本地检索基线上得到稳定引用", async () => {
  const knowledge = createKnowledge();
  const results = await knowledge.search("doctor", "青霉素过敏");
  assert.equal(results[0].documentId, "drug-label-amoxicillin-clavulanate");
  assert.equal(results[0].retrievalStrategyVersion, "poc-hybrid-tfidf-rag-0.1");
  assert.ok(results[0].retrieval.tfidfCosine > 0);
  assert.ok(results[0].retrieval.lexical > 0);
});

test("知识管理员可下架文档，医生不能修改知识状态", async () => {
  const knowledge = createKnowledge();
  assert.throws(() => knowledge.transition("doctor", "poc-followup-sop", "expired"), (error) => error instanceof WorkflowError && error.code === "ACCESS_DENIED");
  const updated = knowledge.transition("knowledge_admin", "poc-followup-sop", "expired");
  assert.equal(updated.status, "expired");
  assert.deepEqual(await knowledge.search("doctor", "随访"), []);
});

test("文本知识导入后保持待审核状态且不参与检索", async () => {
  const knowledge = createKnowledge();
  const imported = await knowledge.import("knowledge_admin", textSource({
    title: "高血压出院后监测指引（模拟）",
    version: "0.1",
    owner: "护理部（模拟）",
    sourceFileName: "hypertension-followup.md",
    sourceFormat: "md",
    effectiveFrom: "2026-01-01",
    effectiveUntil: "2027-01-01",
    content: "# 高血压出院后监测\n\n患者应按约定记录血压，并在出现持续异常时联系随访团队。"
  }));
  assert.equal(imported.status, "review_pending");
  assert.equal(imported.chunkCount, 1);
  assert.deepEqual(await knowledge.search("doctor", "持续异常血压"), []);
  assert.equal(knowledge.audit("knowledge_admin")[0].eventType, "knowledge_imported");
});

test("知识管理员发布已导入文本后可被检索，过期后立即排除", async () => {
  const knowledge = createKnowledge();
  const imported = await knowledge.import("knowledge_admin", textSource({
    title: "高血压出院后监测指引（模拟）",
    version: "0.1",
    owner: "护理部（模拟）",
    sourceFileName: "hypertension-followup.txt",
    sourceFormat: "txt",
    effectiveFrom: "2026-01-01",
    effectiveUntil: "2027-01-01",
    content: "患者应按约定记录家庭血压；若连续三次收缩压异常，应由随访团队复核并联系经治医生。"
  }));
  knowledge.transition("knowledge_admin", imported.documentId, "published");
  const results = await knowledge.search("doctor", "连续三次收缩压异常");
  assert.equal(results[0].documentId, imported.documentId);
  knowledge.transition("knowledge_admin", imported.documentId, "expired");
  assert.deepEqual(await knowledge.search("doctor", "连续三次收缩压异常"), []);
});

test("导入和生命周期操作都受知识管理员权限与状态机约束", async () => {
  const knowledge = createKnowledge();
  const input = {
    title: "模拟文本", version: "0.1", owner: "护理部（模拟）", sourceFileName: "source.txt", sourceFormat: "txt",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "这是一段满足最小长度要求的模拟知识正文，用于验证导入权限控制。"
  };
  await assert.rejects(knowledge.import("doctor", textSource(input)), (error) => error instanceof WorkflowError && error.code === "ACCESS_DENIED");
  const imported = await knowledge.import("knowledge_admin", textSource(input));
  assert.throws(() => knowledge.transition("knowledge_admin", imported.documentId, "expired"), (error) => error instanceof WorkflowError && error.code === "KNOWLEDGE_STATE_CONFLICT");
  await assert.rejects(knowledge.import("knowledge_admin", textSource(input)), (error) => error instanceof WorkflowError && error.code === "DUPLICATE_KNOWLEDGE_CONTENT");
});

test("待审核文档可撤回且不可再发布或检索", async () => {
  const knowledge = createKnowledge();
  const imported = await knowledge.import("knowledge_admin", textSource({
    title: "撤回验证文本", version: "0.1", owner: "护理部（模拟）", sourceFileName: "withdraw.txt", sourceFormat: "txt",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "这是一段用于验证知识管理员撤回待审核文本的模拟知识正文，撤回后不得再次发布。"
  }));
  const withdrawn = knowledge.transition("knowledge_admin", imported.documentId, "withdrawn");
  assert.equal(withdrawn.status, "withdrawn");
  assert.throws(() => knowledge.transition("knowledge_admin", imported.documentId, "published"), (error) => error instanceof WorkflowError && error.code === "KNOWLEDGE_STATE_CONFLICT");
  assert.deepEqual(await knowledge.search("doctor", "撤回验证文本"), []);
});

test("异步知识入库任务完成后才创建待审核文档", async () => {
  const knowledge = createKnowledge();
  const queued = knowledge.startImport("knowledge_admin", textSource({
    title: "异步入库验证", version: "0.1", owner: "护理部（模拟）", sourceFileName: "async-import.md", sourceFormat: "md",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "该模拟文档用于验证异步解析任务完成后才创建可见的待审核知识文档。"
  }));
  assert.equal(queued.status, "queued");
  assert.equal(knowledge.list("knowledge_admin").some((document) => document.title === "异步入库验证"), false);
  const completed = await completedJob(knowledge, queued.jobId);
  assert.equal(completed.status, "review_pending");
  assert.ok(completed.documentId);
  assert.equal(knowledge.list("knowledge_admin").find((document) => document.documentId === completed.documentId).status, "review_pending");
});

test("可重试解析失败任务可在后续尝试中恢复", async () => {
  let shouldFail = true;
  const knowledge = createKnowledge({
    parseSource: async (input) => {
      if (shouldFail) throw new DocumentParseError("DOCUMENT_PARSE_FAILED", "模拟临时解析故障");
      return parseKnowledgeSource(input);
    }
  });
  const queued = knowledge.startImport("knowledge_admin", textSource({
    title: "重试入库验证", version: "0.1", owner: "护理部（模拟）", sourceFileName: "retry-import.txt", sourceFormat: "txt",
    effectiveFrom: "2026-01-01", effectiveUntil: "2027-01-01", content: "该模拟文档用于验证解析任务失败后可追溯重试并恢复为待审核状态。"
  }));
  const failed = await completedJob(knowledge, queued.jobId);
  assert.equal(failed.status, "failed");
  assert.equal(failed.error.code, "DOCUMENT_PARSE_FAILED");
  assert.equal(failed.error.retryable, true);
  shouldFail = false;
  const retried = knowledge.retryImport("knowledge_admin", queued.jobId);
  assert.equal(retried.attempt, 2);
  const completed = await completedJob(knowledge, queued.jobId);
  assert.equal(completed.status, "review_pending");
  assert.throws(() => knowledge.getImportJob("doctor", queued.jobId), (error) => error instanceof WorkflowError && error.code === "ACCESS_DENIED");
});

test("知识资产和入库任务可在重建注册表后恢复", async () => {
  const runtime = createRuntimeStatePath();
  try {
    const first = new KnowledgeRegistry({ runtimeStatePath: runtime.runtimeStatePath });
    const queued = first.startImport("knowledge_admin", textSource({
      title: "持久化恢复验证",
      version: "0.1",
      owner: "护理部（模拟）",
      sourceFileName: "persisted-import.md",
      sourceFormat: "md",
      effectiveFrom: "2026-01-01",
      effectiveUntil: "2027-01-01",
      content: "该模拟文档用于验证知识资产和入库任务在服务重启后仍可恢复。"
    }));
    const completed = await completedJob(first, queued.jobId);
    first.transition("knowledge_admin", completed.documentId, "published");

    const second = new KnowledgeRegistry({ runtimeStatePath: runtime.runtimeStatePath });
    const restoredJob = second.getImportJob("knowledge_admin", queued.jobId);
    assert.equal(restoredJob.status, "review_pending");
    assert.equal(restoredJob.documentId, completed.documentId);
    assert.equal(second.list("knowledge_admin").some((document) => document.documentId === completed.documentId), true);

    const results = await second.search("doctor", "服务重启后仍可恢复");
    assert.equal(results[0].documentId, completed.documentId);
  } finally {
    runtime.cleanup();
  }
});

test("知识管理员可恢复预置样例并清空运行时状态文件", async () => {
  const runtime = createRuntimeStatePath();
  try {
    const knowledge = new KnowledgeRegistry({ runtimeStatePath: runtime.runtimeStatePath });
    const imported = await knowledge.import("knowledge_admin", textSource({
      title: "运行时重置验证",
      version: "0.1",
      owner: "护理部（模拟）",
      sourceFileName: "runtime-reset.txt",
      sourceFormat: "txt",
      effectiveFrom: "2026-01-01",
      effectiveUntil: "2027-01-01",
      content: "该模拟文档用于验证恢复预置样例后，运行时导入结果不会继续残留。"
    }));
    assert.equal(existsSync(runtime.runtimeStatePath), true);
    assert.equal(knowledge.list("knowledge_admin").some((document) => document.documentId === imported.documentId), true);

    const reset = knowledge.resetRuntime("knowledge_admin");
    assert.equal(reset.documentCount, 3);
    assert.equal(reset.importJobCount, 0);
    assert.equal(existsSync(runtime.runtimeStatePath), false);

    const restored = new KnowledgeRegistry({ runtimeStatePath: runtime.runtimeStatePath });
    assert.equal(restored.list("knowledge_admin").length, 3);
    assert.equal(restored.list("knowledge_admin").some((document) => document.documentId === imported.documentId), false);
    assert.equal(restored.listImportJobs("knowledge_admin").length, 0);
  } finally {
    runtime.cleanup();
  }
});

test("语义索引已初始化后，新发布文档仍进入混合检索候选集", async () => {
  const knowledge = createKnowledge({ enableSemantic: true });
  await knowledge.search("doctor", "青霉素过敏");
  const imported = await knowledge.import("knowledge_admin", textSource({
    title: "高血压出院后监测指引（语义验证）",
    version: "0.1",
    owner: "护理部（模拟）",
    sourceFileName: "hypertension-semantic.md",
    sourceFormat: "md",
    effectiveFrom: "2026-01-01",
    effectiveUntil: "2027-01-01",
    content: "患者应按约定记录家庭血压；若连续三次收缩压异常，应由随访团队复核并联系经治医生。"
  }));
  knowledge.transition("knowledge_admin", imported.documentId, "published");
  const results = await knowledge.search("doctor", "连续三次收缩压异常");
  assert.ok(results.some((result) => result.documentId === imported.documentId));
});

test("必需知识下架后工作流明确降级", () => {
  const knowledge = createKnowledge();
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  knowledge.transition("knowledge_admin", "poc-followup-sop", "expired");
  workflow.reset("doctor");
  assert.throws(() => workflow.runAnalysis("doctor"), (error) => error instanceof WorkflowError && error.code === "INSUFFICIENT_EVIDENCE");
  assert.equal(workflow.overview("doctor").case.state, "failed");
});

test("缺少必要知识版本时工作流可降级初始化而不阻断服务启动", () => {
  const knowledge = createKnowledge();
  knowledge.transition("knowledge_admin", "poc-followup-sop", "expired");
  const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
  assert.equal(workflow.overview("doctor").case.state, "failed");
  assert.equal(workflow.risks.length, 0);
});
