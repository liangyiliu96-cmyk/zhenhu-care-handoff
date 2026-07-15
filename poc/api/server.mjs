import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { PocWorkflow, WorkflowError } from "./workflow.mjs";
import { KnowledgeRegistry } from "./knowledge.mjs";

const webRoot = resolve(process.cwd(), "poc", "web");
const port = Number(process.env.PORT ?? 4173);
const maxJsonBodyBytes = 8 * 1024 * 1024;
const knowledge = new KnowledgeRegistry({ enableSemantic: true });
const workflow = new PocWorkflow({ knowledgeRegistry: knowledge });
const mimeTypes = { ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml" };

function send(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "http://127.0.0.1:4173" });
  response.end(JSON.stringify(payload));
}

function roleFor(request) {
  const role = request.headers["x-demo-role"];
  return ["doctor", "nurse", "case_manager", "auditor", "knowledge_admin"].includes(role) ? role : "unauthenticated";
}

function requestIdFor(request) {
  return request.headers["x-request-id"] ?? `req-${Date.now()}`;
}

async function bodyOf(request) {
  let body = "";
  let byteLength = 0;
  for await (const chunk of request) {
    byteLength += chunk.length;
    if (byteLength > maxJsonBodyBytes) throw new WorkflowError(413, "REQUEST_BODY_TOO_LARGE", "PoC 请求体超过 8 MiB 限制");
    body += chunk;
  }
  if (!body) return {};
  try { return JSON.parse(body); } catch { throw new WorkflowError(400, "VALIDATION_ERROR", "请求体不是合法 JSON"); }
}

function apiPayload(request, data, caseId = "CASE-2026-0715-0042") {
  return { request_id: requestIdFor(request), case_id: caseId, data, error: null };
}

async function handleApi(request, response, url) {
  if (request.method === "OPTIONS") {
    response.writeHead(204, { "Access-Control-Allow-Origin": "http://127.0.0.1:4173", "Access-Control-Allow-Headers": "Content-Type, X-Demo-Role, X-Request-Id, X-Use-Purpose", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" });
    response.end();
    return;
  }
  if (request.method === "GET" && url.pathname === "/healthz") {
    send(response, 200, { status: "ok", service: "zhenhu-poc-api", workflow_state: workflow.case.state, knowledge: knowledge.health() });
    return;
  }
  if (request.headers["x-use-purpose"] !== "poc-review") throw new WorkflowError(400, "VALIDATION_ERROR", "缺少 PoC 请求用途");
  const role = roleFor(request);
  const pathname = url.pathname;
  const caseMatch = pathname.match(/^\/api\/v1\/cases\/([^/]+)/);
  if (caseMatch && caseMatch[1] !== "CASE-2026-0715-0042") throw new WorkflowError(404, "CASE_NOT_FOUND", "找不到模拟病例");

  if (request.method === "GET" && pathname === "/api/v1/knowledge/documents") {
    send(response, 200, apiPayload(request, knowledge.list(role), null));
    return;
  }
  if (request.method === "GET" && pathname === "/api/v1/knowledge/search") {
    send(response, 200, apiPayload(request, await knowledge.search(role, url.searchParams.get("q") ?? ""), null));
    return;
  }
  if (request.method === "GET" && pathname === "/api/v1/knowledge/audit") {
    send(response, 200, apiPayload(request, knowledge.audit(role), null));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/knowledge/documents/import") {
    send(response, 202, apiPayload(request, knowledge.startImport(role, await bodyOf(request)), null));
    return;
  }
  if (request.method === "GET" && pathname === "/api/v1/knowledge/import-jobs") {
    send(response, 200, apiPayload(request, knowledge.listImportJobs(role), null));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/knowledge/runtime/reset") {
    send(response, 200, apiPayload(request, knowledge.resetRuntime(role), null));
    return;
  }
  const importJob = pathname.match(/^\/api\/v1\/knowledge\/import-jobs\/([^/]+)$/);
  if (request.method === "GET" && importJob) {
    send(response, 200, apiPayload(request, knowledge.getImportJob(role, importJob[1]), null));
    return;
  }
  const retryImportJob = pathname.match(/^\/api\/v1\/knowledge\/import-jobs\/([^/]+)\/retry$/);
  if (request.method === "POST" && retryImportJob) {
    send(response, 202, apiPayload(request, knowledge.retryImport(role, retryImportJob[1]), null));
    return;
  }
  const knowledgeTransition = pathname.match(/^\/api\/v1\/knowledge\/documents\/([^/]+)\/transition$/);
  if (request.method === "POST" && knowledgeTransition) {
    const body = await bodyOf(request);
    const updated = knowledge.transition(role, knowledgeTransition[1], body.status);
    // 需求 §4.4：已发布知识过期/撤回/被替代时，阻断引用它的在办病例。
    if (["expired", "withdrawn", "superseded"].includes(updated.status)) {
      workflow.onKnowledgeUnavailable(updated.documentId, role);
    }
    send(response, 200, apiPayload(request, updated, null));
    return;
  }

  if (request.method === "GET" && pathname === "/api/v1/cases/CASE-2026-0715-0042/overview") {
    send(response, 200, apiPayload(request, workflow.overview(role)));
    return;
  }
  if (request.method === "GET" && pathname === "/api/v1/tasks") {
    send(response, 200, apiPayload(request, workflow.listTasks(role)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/demo/reset") {
    const body = await bodyOf(request);
    workflow.requireRole(role, ["doctor"]);
    workflow.reset(role);
    try {
      workflow.runAnalysis(role, {
        dependencyFailure: body.scenario === "dependency_failure",
        knowledgeExpired: body.scenario === "knowledge_expired",
        dataConflict: body.scenario === "data_conflict"
      });
    } catch (error) {
      if (body.interactive && error instanceof WorkflowError && ["INSUFFICIENT_EVIDENCE", "DEPENDENCY_UNAVAILABLE"].includes(error.code)) {
        send(response, 200, apiPayload(request, workflow.overview(role)));
        return;
      }
      throw error;
    }
    send(response, 200, apiPayload(request, workflow.overview(role)));
    return;
  }
  const reviewMatch = pathname.match(/^\/api\/v1\/cases\/CASE-2026-0715-0042\/risks\/([^/]+)\/review$/);
  if (request.method === "POST" && reviewMatch) {
    const body = await bodyOf(request);
    send(response, 200, apiPayload(request, workflow.reviewRisk(role, reviewMatch[1], body.action, body.note, body.reason)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/cases/CASE-2026-0715-0042/task-drafts") {
    send(response, 201, apiPayload(request, workflow.createTaskDraft(role)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/cases/CASE-2026-0715-0042/task-drafts/draft-2026-0715-0042-01/simulated-publish") {
    send(response, 200, apiPayload(request, workflow.publish(role)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/cases/CASE-2026-0715-0042/cancel") {
    send(response, 200, apiPayload(request, workflow.cancel(role)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/cases/CASE-2026-0715-0042/close") {
    send(response, 200, apiPayload(request, workflow.close(role)));
    return;
  }
  if (request.method === "POST" && pathname === "/api/v1/cases/CASE-2026-0715-0042/reconcile") {
    send(response, 200, apiPayload(request, workflow.reconcile(role)));
    return;
  }
  const supplementMatch = pathname.match(/^\/api\/v1\/cases\/CASE-2026-0715-0042\/tasks\/([^/]+)\/supplement$/);
  if (request.method === "POST" && supplementMatch) {
    const body = await bodyOf(request);
    send(response, 200, apiPayload(request, workflow.supplementTask(role, supplementMatch[1], body)));
    return;
  }
  throw new WorkflowError(404, "ROUTE_NOT_FOUND", "找不到接口");
}

function serveStatic(request, response, url) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }
  const relativePath = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const filePath = resolve(webRoot, relativePath);
  if (filePath !== webRoot && !filePath.startsWith(`${webRoot}${sep}`)) {
    response.writeHead(403); response.end("Forbidden"); return;
  }
  try {
    if (!statSync(filePath).isFile()) throw new Error("Not a file");
    response.writeHead(200, { "Content-Type": mimeTypes[extname(filePath)] ?? "application/octet-stream" });
    if (request.method === "HEAD") { response.end(); return; }
    createReadStream(filePath).pipe(response);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  try {
    if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") await handleApi(request, response, url);
    else serveStatic(request, response, url);
  } catch (error) {
    const known = error instanceof WorkflowError ? error : new WorkflowError(500, "INTERNAL_ERROR", "服务端发生未预期错误");
    if (url.pathname.startsWith("/api/") && request.method !== "GET" && known.code === "ACCESS_DENIED") {
      workflow.recordDenied(roleFor(request), `${request.method} ${url.pathname}`);
    }
    send(response, known.status, { request_id: requestIdFor(request), case_id: "CASE-2026-0715-0042", data: null, error: { code: known.code, message: known.message, details: known.details } });
  }
}).listen(port, "127.0.0.1", () => console.log(`PoC API and Web are running at http://127.0.0.1:${port}`));
