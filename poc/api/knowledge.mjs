import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";
import { WorkflowError } from "./workflow.mjs";
import { LocalTfidfIndex } from "./retrieval.mjs";
import { MultilingualEmbeddingIndex, EMBEDDING_MODEL } from "./embedding.mjs";
import { DocumentParseError, parseKnowledgeSource } from "./document-parser.mjs";

const sourcePath = resolve(process.cwd(), "poc", "knowledge", "documents.json");
const runtimeStatePath = resolve(process.cwd(), "poc", "data", "runtime", "knowledge-state.json");
const copy = (value) => structuredClone(value);
const allowedRoles = ["doctor", "auditor", "knowledge_admin"];
// 知识文档版本状态机，对照需求 §4.4：review_pending -> published | withdrawn | review_rejected；
// published -> expired | withdrawn | superseded | archived。过期/撤回/被替代后不再参与检索。
const transitionTargets = {
  review_pending: new Set(["published", "withdrawn", "review_rejected"]),
  published: new Set(["expired", "withdrawn", "superseded", "archived"]),
  expired: new Set(),
  withdrawn: new Set(),
  superseded: new Set(),
  archived: new Set(),
  review_rejected: new Set()
};
const retryableIngestionErrors = new Set(["DOCUMENT_PARSE_FAILED", "INTERNAL_ERROR"]);

function isAvailable(document) {
  const today = new Date().toISOString().slice(0, 10);
  return document.status === "published" && document.effectiveFrom <= today && document.effectiveUntil >= today;
}

function validDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

function normalizedContent(content) {
  return content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[ \t]+\n/g, "\n").trim();
}

function splitParagraph(paragraph, maxLength) {
  if (paragraph.length <= maxLength) return [paragraph];
  const sentences = paragraph.match(/[^。！？；\n]+[。！？；]?/g) ?? [paragraph];
  const parts = [];
  let current = "";
  for (let sentence of sentences) {
    if (current && current.length + sentence.length > maxLength) {
      parts.push(current);
      current = "";
    }
    while (sentence.length > maxLength) {
      if (current) { parts.push(current); current = ""; }
      parts.push(sentence.slice(0, maxLength));
      sentence = sentence.slice(maxLength);
    }
    current += sentence;
  }
  if (current) parts.push(current);
  return parts;
}

function chunkContent(content) {
  const paragraphs = normalizedContent(content).split(/\n\s*\n+/).filter(Boolean);
  const chunks = [];
  let buffer = "";
  for (const paragraph of paragraphs.flatMap((item) => splitParagraph(item, 420))) {
    if (buffer && buffer.length + paragraph.length + 1 > 420) {
      chunks.push(buffer);
      buffer = "";
    }
    buffer = buffer ? `${buffer}\n${paragraph}` : paragraph;
  }
  if (buffer) chunks.push(buffer);
  return chunks.map((text, index) => ({
    chunkId: `chunk-import-${String(index + 1).padStart(3, "0")}`,
    location: `自动分块 ${String(index + 1).padStart(2, "0")}`,
    text
  }));
}

function citation(document, chunk, retrieval = {}) {
  // 引用结构对照需求 §4.3：document_id、版本、章节/段落坐标、chunk_id、原文片段、检索时间与检索策略版本。
  // 坐标是不可变审计证据，不随界面或索引变化而改变。
  return {
    label: `${document.title} · ${document.version}`,
    documentId: document.documentId,
    version: document.version,
    chunkId: chunk.chunkId,
    location: chunk.location,
    coordinates: chunk.location,
    retrievedAt: new Date().toISOString(),
    excerpt: chunk.text,
    status: document.status,
    retrievalStrategyVersion: retrieval.strategy ?? "poc-structured-retrieval-0.1",
    score: retrieval.score,
    retrieval: retrieval.metrics
  };
}

function persistedStateFrom(seedDocuments) {
  return {
    schemaVersion: 1,
    documents: copy(seedDocuments),
    auditEvents: [],
    ingestionJobs: [],
    nextIngestionJob: 1
  };
}

export class KnowledgeRegistry {
  constructor({
    enableSemantic = false,
    parseSource = parseKnowledgeSource,
    documentsPath = sourcePath,
    runtimeStatePath: statePath = runtimeStatePath,
    persistRuntime = true
  } = {}) {
    this.enableSemantic = enableSemantic;
    this.parseSource = parseSource;
    this.documentsPath = documentsPath;
    this.runtimeStatePath = statePath;
    this.persistRuntime = persistRuntime;
    this.seedDocuments = JSON.parse(readFileSync(this.documentsPath, "utf8"));
    this.loadState();
    this.rebuildIndex();
  }

  loadState() {
    const fallback = persistedStateFrom(this.seedDocuments);
    if (!this.persistRuntime || !existsSync(this.runtimeStatePath)) {
      this.documents = fallback.documents;
      this.auditEvents = fallback.auditEvents;
      this.ingestionJobs = fallback.ingestionJobs;
      this.nextIngestionJob = fallback.nextIngestionJob;
      return;
    }
    try {
      const parsed = JSON.parse(readFileSync(this.runtimeStatePath, "utf8"));
      this.documents = Array.isArray(parsed.documents) ? parsed.documents : fallback.documents;
      this.auditEvents = Array.isArray(parsed.auditEvents) ? parsed.auditEvents : fallback.auditEvents;
      this.ingestionJobs = Array.isArray(parsed.ingestionJobs) ? parsed.ingestionJobs : fallback.ingestionJobs;
      this.nextIngestionJob = Number.isInteger(parsed.nextIngestionJob) && parsed.nextIngestionJob > 0 ? parsed.nextIngestionJob : fallback.nextIngestionJob;
    } catch {
      this.documents = fallback.documents;
      this.auditEvents = fallback.auditEvents;
      this.ingestionJobs = fallback.ingestionJobs;
      this.nextIngestionJob = fallback.nextIngestionJob;
    }
  }

  persistState() {
    if (!this.persistRuntime) return;
    mkdirSync(dirname(this.runtimeStatePath), { recursive: true });
    writeFileSync(this.runtimeStatePath, JSON.stringify({
      schemaVersion: 1,
      documents: this.documents,
      auditEvents: this.auditEvents,
      ingestionJobs: this.ingestionJobs,
      nextIngestionJob: this.nextIngestionJob
    }, null, 2), "utf8");
  }

  rebuildIndex() {
    const available = this.documents.filter(isAvailable);
    this.index = new LocalTfidfIndex(available);
    this.semanticIndex = this.enableSemantic ? new MultilingualEmbeddingIndex(available) : null;
  }

  requireRole(role, allowed = allowedRoles) {
    if (!allowed.includes(role)) throw new WorkflowError(403, "ACCESS_DENIED", "当前角色无权访问知识资产");
  }

  publicDocument(document) {
    const { chunks, ...summary } = document;
    return { ...summary, chunkCount: chunks.length, available: isAvailable(document) };
  }

  record(actor, eventType, document, detail) {
    this.auditEvents.unshift({
      auditId: `knowledge-audit-${this.auditEvents.length + 1}`,
      occurredAt: new Date().toISOString(),
      actor,
      eventType,
      documentId: document.documentId,
      title: document.title,
      detail
    });
  }

  list(role) {
    this.requireRole(role);
    return copy(this.documents.map((document) => this.publicDocument(document)));
  }

  audit(role) {
    this.requireRole(role, ["knowledge_admin", "auditor"]);
    return copy(this.auditEvents);
  }

  validateImport(role, input) {
    this.requireRole(role, ["knowledge_admin"]);
    const title = typeof input?.title === "string" ? input.title.trim() : "";
    const version = typeof input?.version === "string" ? input.version.trim() : "";
    const owner = typeof input?.owner === "string" ? input.owner.trim() : "";
    if (!title || !version || !owner) throw new WorkflowError(400, "VALIDATION_ERROR", "知识导入缺少标题、版本或责任部门");
    if (!validDate(input.effectiveFrom) || !validDate(input.effectiveUntil) || input.effectiveFrom > input.effectiveUntil) throw new WorkflowError(400, "VALIDATION_ERROR", "知识生效日期不合法");
  }

  publicJob(job) {
    return {
      jobId: job.jobId,
      status: job.status,
      attempt: job.attempt,
      createdAt: job.createdAt,
      startedAt: job.startedAt,
      completedAt: job.completedAt,
      documentId: job.documentId,
      title: job.input.title,
      sourceFileName: job.input.sourceFileName,
      sourceFormat: job.input.sourceFormat,
      error: job.error
    };
  }

  recordJob(actor, eventType, job, detail) {
    this.auditEvents.unshift({
      auditId: `knowledge-audit-${this.auditEvents.length + 1}`,
      occurredAt: new Date().toISOString(),
      actor,
      eventType,
      jobId: job.jobId,
      title: job.input.title,
      detail
    });
  }

  startImport(role, input) {
    this.validateImport(role, input);
    const job = {
      jobId: `knowledge-ingestion-${String(this.nextIngestionJob++).padStart(4, "0")}`,
      actor: role,
      input: copy(input),
      status: "queued",
      attempt: 1,
      createdAt: new Date().toISOString(),
      startedAt: null,
      completedAt: null,
      documentId: null,
      error: null
    };
    this.ingestionJobs.unshift(job);
    this.recordJob(role, "knowledge_ingestion_queued", job, "知识文件已进入解析与入库队列");
    this.persistState();
    this.scheduleImport(job);
    return copy(this.publicJob(job));
  }

  scheduleImport(job) {
    setTimeout(() => { void this.processImportJob(job); }, 0);
  }

  async processImportJob(job) {
    job.status = "parsing";
    job.startedAt = new Date().toISOString();
    job.error = null;
    this.persistState();
    try {
      const document = await this.import(job.actor, job.input);
      job.status = "review_pending";
      job.documentId = document.documentId;
      job.completedAt = new Date().toISOString();
      this.recordJob(job.actor, "knowledge_ingestion_completed", job, `解析与入库完成，文档进入 ${document.status}`);
      this.persistState();
    } catch (error) {
      const known = error instanceof WorkflowError ? error : new WorkflowError(500, "INTERNAL_ERROR", "知识入库任务发生未预期错误");
      job.status = "failed";
      job.completedAt = new Date().toISOString();
      job.error = { code: known.code, message: known.message, retryable: retryableIngestionErrors.has(known.code) };
      this.recordJob(job.actor, "knowledge_ingestion_failed", job, `解析与入库失败：${known.code}`);
      this.persistState();
    }
  }

  listImportJobs(role) {
    this.requireRole(role, ["knowledge_admin"]);
    return copy(this.ingestionJobs.map((job) => this.publicJob(job)));
  }

  getImportJob(role, jobId) {
    this.requireRole(role, ["knowledge_admin"]);
    const job = this.ingestionJobs.find((item) => item.jobId === jobId);
    if (!job) throw new WorkflowError(404, "INGESTION_JOB_NOT_FOUND", "找不到知识入库任务");
    return copy(this.publicJob(job));
  }

  retryImport(role, jobId) {
    this.requireRole(role, ["knowledge_admin"]);
    const job = this.ingestionJobs.find((item) => item.jobId === jobId);
    if (!job) throw new WorkflowError(404, "INGESTION_JOB_NOT_FOUND", "找不到知识入库任务");
    if (job.status !== "failed") throw new WorkflowError(409, "INGESTION_JOB_STATE_CONFLICT", "只有失败的知识入库任务可以重试");
    if (!job.error?.retryable) throw new WorkflowError(409, "INGESTION_JOB_NOT_RETRYABLE", "当前失败原因不允许直接重试，请修正源文件后重新导入");
    job.status = "queued";
    job.attempt += 1;
    job.startedAt = null;
    job.completedAt = null;
    job.error = null;
    this.recordJob(role, "knowledge_ingestion_retried", job, `知识入库任务第 ${job.attempt} 次进入队列`);
    this.persistState();
    this.scheduleImport(job);
    return copy(this.publicJob(job));
  }

  async import(role, input) {
    this.validateImport(role, input);
    const title = input.title.trim();
    const version = input.version.trim();
    const owner = input.owner.trim();
    let source;
    try {
      source = await this.parseSource(input);
    } catch (error) {
      if (error instanceof DocumentParseError) throw new WorkflowError(400, error.code, error.message);
      throw error;
    }
    const contentHash = createHash("sha256").update(source.content, "utf8").digest("hex");
    if (this.documents.some((document) => document.contentHash === contentHash)) throw new WorkflowError(409, "DUPLICATE_KNOWLEDGE_CONTENT", "相同内容已存在于知识资产中");
    const chunks = chunkContent(source.content);
    const document = {
      documentId: `poc-import-${contentHash.slice(0, 12)}`,
      title,
      version,
      status: "review_pending",
      owner,
      effectiveFrom: input.effectiveFrom,
      effectiveUntil: input.effectiveUntil,
      sourceFileName: source.sourceFileName,
      sourceFormat: source.sourceFormat,
      sourceMime: source.sourceMime,
      sourceByteLength: source.sourceByteLength,
      sourceHash: source.sourceHash,
      contentHash,
      importedAt: new Date().toISOString(),
      chunks
    };
    this.documents.push(document);
    this.rebuildIndex();
    this.record(role, "knowledge_imported", document, `导入 ${source.sourceFileName}，完成 ${source.sourceFormat.toUpperCase()} 解析并生成 ${chunks.length} 个稳定分块，等待发布审核`);
    this.persistState();
    return copy(this.publicDocument(document));
  }

  async search(role, query) {
    this.requireRole(role);
    if (!query.trim()) throw new WorkflowError(400, "VALIDATION_ERROR", "请输入检索关键词");
    const local = this.index.search(query);
    if (!this.semanticIndex) return local.map((result) => citation(result.document, result.chunk, {
      strategy: "poc-hybrid-tfidf-rag-0.1", score: result.score, metrics: { tfidfCosine: Number(result.cosineScore.toFixed(4)), lexical: Number(result.lexicalScore.toFixed(4)) }
    }));
    try {
      const semantic = await this.semanticIndex.search(query);
      const localByChunk = new Map(local.map((result) => [`${result.document.documentId}:${result.chunk.chunkId}`, result]));
      const semanticByChunk = new Map(semantic.map((result) => [`${result.document.documentId}:${result.chunk.chunkId}`, result]));
      const candidateKeys = new Set([
        ...localByChunk.keys(),
        ...semantic.filter((result) => result.score >= 0.35).map((result) => `${result.document.documentId}:${result.chunk.chunkId}`)
      ]);
      return [...candidateKeys].map((key) => {
        const localResult = localByChunk.get(key);
        const semanticResult = semanticByChunk.get(key);
        const result = localResult ?? semanticResult;
        const localScore = localResult?.score ?? 0;
        const semanticScore = Math.max(0, semanticResult?.score ?? 0);
        const score = Number((semanticScore * 0.65 + localScore * 0.35).toFixed(4));
        return citation(result.document, result.chunk, {
          strategy: "poc-multilingual-embedding-hybrid-rag-0.1",
          score,
          metrics: { semanticCosine: semanticResult?.score ?? 0, localHybrid: localScore, model: EMBEDDING_MODEL }
        });
      }).filter((item) => item.score > 0).sort((left, right) => right.score - left.score);
    } catch (error) {
      return local.map((result) => citation(result.document, result.chunk, {
        strategy: "poc-tfidf-explicit-fallback-0.1", score: result.score,
        metrics: { tfidfCosine: Number(result.cosineScore.toFixed(4)), lexical: Number(result.lexicalScore.toFixed(4)), degradedReason: error instanceof Error ? error.message : String(error) }
      }));
    }
  }

  analysisCitations() {
    const find = (id, chunkId) => {
      const document = this.documents.find((item) => item.documentId === id && isAvailable(item));
      const chunk = document?.chunks.find((item) => item.chunkId === chunkId);
      return document && chunk ? citation(document, chunk) : null;
    };
    const citations = {
      drug: find("drug-label-amoxicillin-clavulanate", "chunk-2-4"),
      followupWindow: find("poc-followup-sop", "chunk-3-2"),
      monitoring: find("poc-followup-sop", "chunk-2-4"),
      conflict: find("poc-handoff-sop", "chunk-1-3")
    };
    return Object.values(citations).every(Boolean) ? citations : null;
  }

  transition(role, documentId, status) {
    this.requireRole(role, ["knowledge_admin"]);
    if (!Object.hasOwn(transitionTargets, status)) throw new WorkflowError(400, "VALIDATION_ERROR", "不支持的知识状态");
    const document = this.documents.find((item) => item.documentId === documentId);
    if (!document) throw new WorkflowError(404, "KNOWLEDGE_NOT_FOUND", "找不到知识文档");
    if (!transitionTargets[document.status]?.has(status)) throw new WorkflowError(409, "KNOWLEDGE_STATE_CONFLICT", `知识文档当前状态 ${document.status} 不允许切换到 ${status}`);
    document.status = status;
    this.rebuildIndex();
    this.record(role, "knowledge_status_changed", document, `知识状态切换为 ${status}`);
    this.persistState();
    return copy(this.publicDocument(document));
  }

  resetRuntime(role) {
    this.requireRole(role, ["knowledge_admin"]);
    this.documents = copy(this.seedDocuments);
    this.auditEvents = [];
    this.ingestionJobs = [];
    this.nextIngestionJob = 1;
    this.rebuildIndex();
    // 清除持久化的运行时状态：优先删除文件（恢复到预置样例回退分支）；
    // 若受控环境拦截文件删除，则退而将预置状态写回文件，等价于清除运行时残留。
    if (this.persistRuntime && existsSync(this.runtimeStatePath)) {
      try {
        rmSync(this.runtimeStatePath, { force: true });
      } catch {
        this.persistState();
      }
    }
    return { documentCount: this.documents.length, importJobCount: this.ingestionJobs.length };
  }

  health() {
    return {
      documentCount: this.documents.length,
      searchableCount: this.documents.filter(isAvailable).length,
      importJobCount: this.ingestionJobs.length,
      persistedRuntime: this.persistRuntime && existsSync(this.runtimeStatePath),
      semantic: this.semanticIndex?.status() ?? { state: "disabled" }
    };
  }
}
