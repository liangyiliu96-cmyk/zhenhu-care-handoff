import { assertRoleAccess } from "../../../packages/clinical-contracts/src/index.mjs";

const requiredPortNames = Object.freeze([
  "identityGateway",
  "policyRepository",
  "documentRepository",
  "jobRepository",
  "auditRepository",
  "objectStore",
  "searchIndexGateway",
  "documentParser",
  "malwareScanner",
  "clock"
]);

export function validateKnowledgeServicePorts(ports) {
  const missing = requiredPortNames.filter((name) => typeof ports?.[name] !== "object" && typeof ports?.[name] !== "function");
  if (missing.length) {
    throw new Error(`Missing knowledge service ports: ${missing.join(", ")}`);
  }
  return true;
}

export function createKnowledgeServiceBoundary(ports) {
  validateKnowledgeServicePorts(ports);
  return Object.freeze({
    async authorizeKnowledgeImport(context) {
      assertRoleAccess(context.role, "knowledge_import");
      return ports.identityGateway.resolveActor(context);
    },
    async authorizeKnowledgeRead(context) {
      assertRoleAccess(context.role, "knowledge_documents");
      return ports.identityGateway.resolveActor(context);
    },
    async authorizeRuntimeReset(context) {
      assertRoleAccess(context.role, "knowledge_runtime_reset");
      return ports.identityGateway.resolveActor(context);
    },
    describe() {
      return {
        service: "knowledge-orchestrator",
        requiredPorts: requiredPortNames,
        notes: [
          "正式服务不得直接读取 poc/ 目录数据。",
          "知识对象原件、任务状态和审计必须由外部端口提供。",
          "真实权限由 identityGateway + policyRepository 联合裁决。"
        ]
      };
    }
  });
}

export function listRequiredKnowledgePorts() {
  return [...requiredPortNames];
}
