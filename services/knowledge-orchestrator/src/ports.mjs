import { assertRoleAccess } from "../../../packages/clinical-contracts/src/index.mjs";

const REQUIRED_KNOWLEDGE_PORTS = Object.freeze([
  "identityGateway",
  "policyRepository",
  "documentRepository",
  "jobRepository",
  "auditRepository",
  "objectStore",
  "searchIndexGateway",
  "documentParser",
  "malwareScanner",
  "clock",
]);

function assertPortObject(ports) {
  if (!ports || typeof ports !== "object") {
    throw new TypeError("Knowledge service ports must be an object");
  }
}

export function listRequiredKnowledgePorts() {
  return [...REQUIRED_KNOWLEDGE_PORTS];
}

export function validateKnowledgeServicePorts(ports) {
  assertPortObject(ports);

  for (const name of REQUIRED_KNOWLEDGE_PORTS) {
    if (!(name in ports) || ports[name] == null) {
      throw new Error(`Missing required knowledge service port: ${name}`);
    }
  }

  if (typeof ports.identityGateway.resolveActor !== "function") {
    throw new Error("identityGateway.resolveActor must be a function");
  }

  if (typeof ports.clock.now !== "function") {
    throw new Error("clock.now must be a function");
  }

  return true;
}

export function createKnowledgeServiceBoundary(ports) {
  validateKnowledgeServicePorts(ports);

  async function resolveAuthorizedActor(context, surface) {
    assertRoleAccess(context?.role, surface);
    return ports.identityGateway.resolveActor(context);
  }

  return {
    async authorizeKnowledgeImport(context) {
      return resolveAuthorizedActor(context, "knowledge_import");
    },

    async authorizeRuntimeReset(context) {
      return resolveAuthorizedActor(context, "knowledge_runtime_reset");
    },

    describe() {
      return {
        service: "knowledge-orchestrator",
        requiredPorts: listRequiredKnowledgePorts(),
        notes: [
          "Formal knowledge service boundary; implementations must not import poc/ runtime code.",
          "Ports isolate identity, policy, storage, parsing, scanning, indexing, audit, and time dependencies.",
        ],
      };
    },
  };
}
