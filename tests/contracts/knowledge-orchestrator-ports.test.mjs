import assert from "node:assert/strict";
import test from "node:test";
import { createKnowledgeServiceBoundary, listRequiredKnowledgePorts, validateKnowledgeServicePorts } from "../../services/knowledge-orchestrator/src/index.mjs";

function stubPorts() {
  return {
    identityGateway: { resolveActor: async (context) => ({ actorId: context.actorId ?? "actor-1", role: context.role }) },
    policyRepository: {},
    documentRepository: {},
    jobRepository: {},
    auditRepository: {},
    objectStore: {},
    searchIndexGateway: {},
    documentParser: {},
    malwareScanner: {},
    clock: { now: () => new Date().toISOString() }
  };
}

test("正式知识服务端口列表完整且可校验", () => {
  const ports = stubPorts();
  assert.equal(validateKnowledgeServicePorts(ports), true);
  assert.ok(listRequiredKnowledgePorts().includes("searchIndexGateway"));
  delete ports.objectStore;
  assert.throws(() => validateKnowledgeServicePorts(ports));
});

test("正式知识服务边界只允许授权角色进入关键动作", async () => {
  const service = createKnowledgeServiceBoundary(stubPorts());
  const actor = await service.authorizeKnowledgeImport({ role: "knowledge_admin", actorId: "admin-1" });
  assert.equal(actor.actorId, "admin-1");
  await assert.rejects(service.authorizeRuntimeReset({ role: "doctor", actorId: "doctor-1" }));
});

test("正式知识服务边界会声明与 poc 隔离的依赖原则", () => {
  const service = createKnowledgeServiceBoundary(stubPorts());
  const description = service.describe();
  assert.equal(description.service, "knowledge-orchestrator");
  assert.ok(description.notes.some((item) => item.includes("poc/")));
});
