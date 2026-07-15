// 病例协同工作流。状态机严格对齐 @zhenhu/clinical-contracts（需求 §3.4）：
// draft -> analysing -> review_pending -> confirmed|rejected -> task_draft -> simulated_published -> closed，
// 任意非终态可进入 failed / cancelled；当所引用知识过期/撤回/被替代时进入 knowledge_changed 阻断态。
import { assertCaseTransition } from "../../packages/clinical-contracts/src/index.mjs";

export const CASE_ID = "CASE-2026-0715-0042";
const WORKFLOW_VERSION = "poc-workflow-0.1";

export class WorkflowError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const at = () => new Date().toISOString();
const copy = (value) => structuredClone(value);

function riskItems() {
  return [
    {
      riskId: "risk-allergy-01",
      category: "medication_allergy",
      severity: "high",
      severityLabel: "高风险",
      severityClass: "high",
      type: "确定性规则命中 · 需核实",
      title: "出院药物与已记录过敏史存在潜在冲突",
      summary: "出院带药清单中出现阿莫西林/克拉维酸钾；输入快照记录青霉素类药物致皮疹。系统不作临床结论，请医生核实。",
      status: "pending",
      decision: null,
      evidence: {
        label: "过敏史 · AllergyIntolerance-01",
        resourceType: "AllergyIntolerance",
        resourceRef: "AllergyIntolerance-01",
        fieldPath: "code.text",
        snippet: "青霉素类（皮疹）",
        capturedAt: "2026-07-15T09:10:00.000Z",
        source_type: "source_hybrid"
      },
      citation: {
        label: "药品说明书（模拟片段） · 2025.01",
        documentId: "drug-label-amoxicillin-clavulanate",
        version: "2025.01",
        chunkId: "chunk-2-4",
        location: "禁忌与慎用 · 2.4",
        excerpt: "对青霉素类药物有过敏史者，应由具备处方责任的医师评估。",
        status: "published",
        retrievalStrategyVersion: "mock-rag-0.1"
      }
    },
    {
      riskId: "risk-renal-01",
      category: "followup_window",
      severity: "medium",
      severityLabel: "中风险",
      severityClass: "medium",
      type: "数据一致性 · 需核实",
      title: "肾功能结果与随访计划时间窗不一致",
      summary: "最近肌酐采集时间为出院前 36 小时；随访草稿未包含复查时间。请核实是否需要补充院后监测安排。",
      status: "pending",
      decision: null,
      evidence: {
        label: "检验结果 · Observation-Cr-03",
        resourceType: "Observation",
        resourceRef: "Observation-Cr-03",
        fieldPath: "effectiveDateTime",
        snippet: "肌酐采集时间：出院前 36 小时",
        capturedAt: "2026-07-14T21:10:00.000Z",
        source_type: "source_ehr"
      },
      citation: {
        label: "院内随访 SOP 样例 v0.1 · 3.2",
        documentId: "poc-followup-sop",
        version: "0.1",
        chunkId: "chunk-3-2",
        location: "3.2 · 出院后随访准备",
        excerpt: "复查事项和计划时间应在交接草稿中明确记录。",
        status: "published",
        retrievalStrategyVersion: "mock-rag-0.1"
      }
    },
    {
      riskId: "risk-bp-01",
      category: "missing_field",
      severity: "low",
      severityLabel: "低风险",
      severityClass: "low",
      type: "字段缺失 · 待补充",
      title: "居家血压自测记录字段未见填写",
      summary: "交接单草稿未包含居家自测记录方式。该项仅提示信息完整性，不替代临床判断。",
      status: "pending",
      decision: null,
      evidence: {
        label: "交接草稿 · CarePlan-Draft-01",
        resourceType: "CarePlan",
        resourceRef: "CarePlan-Draft-01",
        fieldPath: "activity.detail.description",
        snippet: "居家血压记录字段为空",
        capturedAt: "2026-07-15T08:55:00.000Z",
        source_type: "source_hybrid"
      },
      citation: {
        label: "院内随访 SOP 样例 v0.1 · 2.4",
        documentId: "poc-followup-sop",
        version: "0.1",
        chunkId: "chunk-2-4",
        location: "2.4 · 居家监测信息",
        excerpt: "交接信息应包含约定的居家监测记录方式。",
        status: "published",
        retrievalStrategyVersion: "mock-rag-0.1"
      }
    },
    {
      riskId: "risk-dose-01",
      category: "dose_discrepancy",
      severity: "medium",
      severityLabel: "中风险",
      severityClass: "medium",
      type: "剂量偏差 · 需核实",
      title: "出院带药剂量与院内用药方案存在偏差",
      summary: "出院带药呋塞米剂量由入院期间 40mg qd 调整为 20mg qd，缺少剂量调整的医嘱说明。系统不作临床结论，请医生核实调整依据。",
      status: "pending",
      decision: null,
      evidence: {
        label: "用药方案 · MedicationRequest-01",
        resourceType: "MedicationRequest",
        resourceRef: "MedicationRequest-01",
        fieldPath: "dosageInstruction.doseAndRate",
        snippet: "呋塞米：入院 40mg qd，出院 20mg qd",
        capturedAt: "2026-07-15T08:50:00.000Z",
        source_type: "source_ehr"
      },
      citation: {
        label: "药品说明书（模拟片段） · 2025.01",
        documentId: "drug-label-furosemide",
        version: "2025.01",
        chunkId: "chunk-3-1",
        location: "用法用量 · 3.1",
        excerpt: "剂量调整应有明确的临床依据并记录于医嘱。",
        status: "published",
        retrievalStrategyVersion: "mock-rag-0.1"
      }
    }
  ];
}

function conflictRisk() {
  return {
    riskId: "risk-allergy-conflict-01",
    category: "source_conflict",
    severity: "high",
    severityLabel: "高风险",
    severityClass: "high",
    type: "来源冲突 · 需人工核实",
    title: "过敏信息在输入来源间存在冲突",
    summary: "过敏资源记录青霉素类致皮疹，出院小结模拟字段记录为“未见明确药物过敏”。系统保留两个来源，不自动选择其中一项。",
    status: "pending",
    decision: null,
    evidence: {
      label: "过敏资源 / 出院小结字段冲突",
      resourceType: "AllergyIntolerance + Composition",
      resourceRef: "AllergyIntolerance-01 / DischargeSummary-02",
      fieldPath: "code.text / section.allergies",
      snippet: "来源 A：青霉素类（皮疹）；来源 B：未见明确药物过敏",
      capturedAt: "2026-07-15T09:10:00.000Z",
      source_type: "source_ehr"
    },
    citation: {
      label: "院内交接 SOP 样例 v0.1 · 1.3",
      documentId: "poc-handoff-sop",
      version: "0.1",
      chunkId: "chunk-1-3",
      location: "1.3 · 冲突信息处理",
      excerpt: "来源信息冲突时，应并列展示并由经治医生完成核实。",
      status: "published",
      retrievalStrategyVersion: "mock-rag-0.1"
    }
  };
}

function snapshot() {
  return {
    snapshotId: "snapshot-2026-0715-0042-v1.3",
    mappingVersion: "poc-fhir-map-0.1",
    capturedAt: "2026-07-15T09:10:00.000Z",
    source: "模拟 FHIR 适配器",
    patient: {
      name: "王某某",
      encounterRef: "IP-2607••42",
      diagnosis: "慢性心力衰竭急性加重",
      dischargeTo: "居家",
      allergy: "青霉素类（皮疹）"
    }
  };
}

export class PocWorkflow {
  constructor({ knowledgeRegistry = null } = {}) {
    this.knowledgeRegistry = knowledgeRegistry;
    this.reset("system");
    try {
      this.runAnalysis("system");
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
    }
  }

  reset(actor) {
    this.case = {
      caseId: CASE_ID,
      state: "draft",
      workflowVersion: WORKFLOW_VERSION,
      inputSnapshotId: "snapshot-2026-0715-0042-v1.3",
      createdAt: at(),
      updatedAt: at()
    };
    this.snapshot = snapshot();
    this.risks = [];
    this.taskDraft = null;
    this.tasks = [];
    this.audit = [];
    this.addAudit(actor, "case_created", "创建模拟病例", "预置脱敏输入快照 v1.3", null, "draft");
  }

  requireRole(role, allowed) {
    if (!allowed.includes(role)) {
      throw new WorkflowError(403, "ACCESS_DENIED", "当前角色无权执行此操作");
    }
  }

  addAudit(actor, eventType, title, detail, before, after) {
    this.audit.unshift({
      auditId: `audit-${this.audit.length + 1}-${Date.now()}`,
      caseId: CASE_ID,
      actor,
      eventType,
      title,
      detail,
      before,
      after,
      occurredAt: at(),
      workflowVersion: WORKFLOW_VERSION
    });
  }

  recordDenied(actor, detail) {
    this.addAudit(actor, "access_denied", "拒绝未授权操作", detail, this.case.state, this.case.state);
  }

  transition(actor, eventType, title, detail, nextState) {
    assertCaseTransition(this.case.state, nextState);
    const before = this.case.state;
    this.case.state = nextState;
    this.case.updatedAt = at();
    this.addAudit(actor, eventType, title, detail, before, nextState);
  }

  runAnalysis(actor, { dependencyFailure = false, knowledgeExpired = false, dataConflict = false } = {}) {
    if (!["draft", "failed", "knowledge_changed"].includes(this.case.state)) {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不允许发起分析", { current_state: this.case.state });
    }
    this.transition(actor, "analysis_started", "启动模拟分析", "执行数据质量规则、确定性规则和模拟知识检索", "analysing");
    if (dependencyFailure) {
      this.transition(actor, "analysis_failed", "模拟检索依赖不可用", "未生成风险项或任务草稿", "failed");
      throw new WorkflowError(503, "DEPENDENCY_UNAVAILABLE", "模拟知识检索依赖不可用");
    }
    if (knowledgeExpired) {
      this.transition(actor, "analysis_failed", "模拟知识版本已过期", "无可用已发布知识版本；未生成风险项或任务草稿", "failed");
      throw new WorkflowError(422, "INSUFFICIENT_EVIDENCE", "模拟知识版本已过期，需人工处理或重新检索");
    }
    const registryCitations = this.knowledgeRegistry?.analysisCitations() ?? null;
    if (this.knowledgeRegistry && !registryCitations) {
      this.transition(actor, "analysis_failed", "缺少有效知识版本", "必要知识未发布、已过期或已下架；未生成风险项或任务草稿", "failed");
      throw new WorkflowError(422, "INSUFFICIENT_EVIDENCE", "缺少有效已发布知识版本");
    }
    this.risks = riskItems();
    if (registryCitations) {
      this.risks[0].citation = registryCitations.drug;
      this.risks[1].citation = registryCitations.followupWindow;
      this.risks[2].citation = registryCitations.monitoring;
    }
    // P0-2: dischargeTo 感知的严重度调整
    const dischargeTo = this.snapshot.patient.dischargeTo;
    if (dischargeTo === "居家") {
      for (const risk of this.risks) {
        if (risk.severity === "medium") {
          risk.severity = "high";
          risk.severityLabel = "高风险（居家升级）";
          risk.severityClass = "high";
        }
      }
    }
    if (dataConflict) {
      const conflict = conflictRisk();
      if (registryCitations) conflict.citation = registryCitations.conflict;
      this.risks.push(conflict);
    }
    this.addAudit("system", "rules_completed", "完成确定性规则校验", `识别 ${this.risks.length} 项待审核风险；规则版本 poc-rules-0.1`, "analysing", "analysing");
    this.addAudit("system", "retrieval_completed", "完成模拟知识检索", "仅返回已发布知识版本；检索策略 mock-rag-0.1", "analysing", "analysing");
    this.transition(actor, "analysis_completed", "分析等待医生审核", "风险项均具备输入证据和已发布知识引用", "review_pending");
  }

  reviewRisk(role, riskId, action, note = "", reason = "") {
    this.requireRole(role, ["doctor"]);
    if (this.case.state !== "review_pending") {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不允许审核风险项", { current_state: this.case.state });
    }
    if (!["confirm", "reject", "edit_confirm", "escalate"].includes(action)) {
      throw new WorkflowError(400, "VALIDATION_ERROR", "不支持的审核动作");
    }
    const risk = this.risks.find((item) => item.riskId === riskId);
    if (!risk) throw new WorkflowError(404, "RISK_NOT_FOUND", "找不到风险项");
    if (risk.status !== "pending") {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "该风险项已完成审核");
    }
    if (action === "escalate") {
      risk.status = "escalated";
      risk.decision = { action: "escalate", reason: reason || note, actor: role, decidedAt: at() };
      this.addAudit(role, "risk_escalated", "升级风险项", `${risk.title}；升级原因：${reason || "（未填写）"}`, "pending", "escalated");
      // escalated 自身不触发状态转移，但需检查是否所有 pending 项已处理完毕
      const pendingAfterEscalate = this.risks.filter((item) => item.status === "pending");
      if (pendingAfterEscalate.length === 0) {
        const anyRejected = this.risks.some((item) => item.status === "rejected");
        this.transition(role, "review_resolved", anyRejected ? "全部风险项已审核，存在驳回项" : "全部风险项已确认", `病例进入 ${anyRejected ? "rejected" : "confirmed"} 状态`, anyRejected ? "rejected" : "confirmed");
      }
      return this.overview(role);
    }
    if (!risk.evidence || !risk.citation || risk.citation.status !== "published") {
      throw new WorkflowError(422, "INSUFFICIENT_EVIDENCE", "风险项缺少有效证据或知识版本");
    }
    risk.status = action === "reject" ? "rejected" : "confirmed";
    risk.decision = { action, note, actor: role, decidedAt: at() };
    this.addAudit(role, "risk_reviewed", action === "reject" ? "驳回风险项" : "确认风险项", `${risk.title}${note ? `；审核说明：${note}` : ""}`, "pending", risk.status);
    const pending = this.risks.filter((item) => item.status === "pending");
    if (pending.length === 0) {
      const anyRejected = this.risks.some((item) => item.status === "rejected");
      this.transition(role, "review_resolved", anyRejected ? "全部风险项已审核，存在驳回项" : "全部风险项已确认", `病例进入 ${anyRejected ? "rejected" : "confirmed"} 状态`, anyRejected ? "rejected" : "confirmed");
    }
    return this.overview(role);
  }

  createTaskDraft(role) {
    this.requireRole(role, ["doctor"]);
    if (!["confirmed", "rejected"].includes(this.case.state)) {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不允许生成任务草稿", { current_state: this.case.state });
    }
    if (this.risks.some((risk) => risk.status === "pending")) {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "仍有待审核风险项");
    }
    if (this.case.state === "knowledge_changed") {
      throw new WorkflowError(409, "KNOWLEDGE_CHANGED", "所引用知识已变化，须重新检索与人工复核后才能生成任务草稿");
    }
    this.taskDraft = {
      draftId: "draft-2026-0715-0042-01",
      caseId: CASE_ID,
      status: "ready",
      sopVersion: "poc-followup-sop-0.1",
      basedOnRiskIds: this.risks.filter((risk) => risk.status === "confirmed").map((risk) => risk.riskId),
      tasks: [
        { taskId: "task-01", taskType: "护理核对", title: "核对出院用药与过敏史记录", assigneeRole: "nurse", due: "出院后 24 小时", escalation: "发现记录不一致时回退医生审核", caseId: CASE_ID, status: "simulated_pending", executionResult: null },
        { taskId: "task-02", taskType: "随访协调", title: "补全居家监测与复查时间安排", assigneeRole: "case_manager", due: "出院后 72 小时", escalation: "无法补全时回退医生审核", caseId: CASE_ID, status: "simulated_pending", executionResult: null }
      ]
    };
    this.transition(role, "task_draft_created", "生成交接与随访任务草稿", "已校验风险项决定、SOP 版本和草稿必填字段", "task_draft");
    return this.overview(role);
  }

  publish(role) {
    this.requireRole(role, ["doctor"]);
    if (this.case.state === "knowledge_changed") {
      throw new WorkflowError(409, "KNOWLEDGE_CHANGED", "所引用知识已变化，已阻断发布，须重新检索与人工复核");
    }
    if (this.case.state !== "task_draft" || !this.taskDraft || this.taskDraft.status !== "ready") {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不允许模拟发布任务草稿", { current_state: this.case.state });
    }
    this.taskDraft.status = "simulated_published";
    this.tasks = this.taskDraft.tasks.map((task) => ({ ...task, status: "simulated_pending", caseId: CASE_ID }));
    this.transition(role, "simulated_publish", "模拟发布任务草稿", "生成 2 个模拟下游待办；未发送通知、未写回业务系统", "simulated_published");
    return this.overview(role);
  }

  cancel(role) {
    this.requireRole(role, ["doctor"]);
    if (["cancelled", "closed"].includes(this.case.state)) {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不可取消", { current_state: this.case.state });
    }
    this.transition(role, "case_cancelled", "取消病例协同", "经治医生取消当前在办病例", "cancelled");
    return this.overview(role);
  }

  close(role) {
    this.requireRole(role, ["doctor"]);
    if (this.case.state !== "simulated_published") {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "仅已模拟发布的病例可关闭", { current_state: this.case.state });
    }
    this.transition(role, "case_closed", "关闭病例协同", "模拟发布后的病例协同已关闭", "closed");
    return this.overview(role);
  }

  reconcile(role) {
    this.requireRole(role, ["doctor"]);
    if (this.case.state !== "knowledge_changed") {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "仅 knowledge_changed 状态可重新核实", { current_state: this.case.state });
    }
    this.reset(role);
    this.runAnalysis(role);
    return this.overview(role);
  }

  // 当所引用知识过期/撤回/被替代时，阻断在办的 review_pending / task_draft 病例，直到重新检索与人工复核。
  onKnowledgeUnavailable(documentId, actor = "system") {
    if (!["review_pending", "task_draft"].includes(this.case.state)) return false;
    const cites = this.risks.some((risk) => risk.citation?.documentId === documentId);
    if (!cites) return false;
    this.taskDraft = null;
    this.tasks = [];
    this.transition(actor, "knowledge_changed", `已发布知识 ${documentId} 过期/撤回/被替代`, "引用该知识的在办病例被阻断，须重新检索与人工复核", "knowledge_changed");
    return true;
  }

  // 护士/个案管理师补充指派给本人的任务执行信息（需求 §3.4）。
  supplementTask(role, taskId, { result = "", note = "" } = {}) {
    this.requireRole(role, ["nurse", "case_manager"]);
    if (!["task_draft", "simulated_published"].includes(this.case.state)) {
      throw new WorkflowError(409, "CASE_STATE_CONFLICT", "当前状态不允许补充任务执行信息", { current_state: this.case.state });
    }
    const task = this.tasks.find((item) => item.taskId === taskId);
    if (!task) throw new WorkflowError(404, "TASK_NOT_FOUND", "找不到模拟任务");
    if (task.assigneeRole !== role) throw new WorkflowError(403, "ACCESS_DENIED", "只能补充指派给本人的任务执行信息");
    task.executionResult = { result, note, supplementedAt: at(), actor: role };
    task.status = "simulated_supplemented";
    this.addAudit(role, "task_supplemented", "补充任务执行信息", `${task.title}${note ? `；说明：${note}` : ""}`, this.case.state, this.case.state);
    return this.overview(role);
  }

  overview(role) {
    this.requireRole(role, ["doctor", "nurse", "case_manager", "auditor"]);
    const result = copy({ case: this.case, snapshot: this.snapshot, risks: this.risks, taskDraft: this.taskDraft, tasks: this.tasks, audit: this.audit });
    if (["nurse", "case_manager"].includes(role)) {
      result.risks = [];
      result.audit = [];
      result.taskDraft = this.case.state === "simulated_published" ? result.taskDraft : null;
      result.tasks = result.tasks.filter((task) => task.assigneeRole === role);
    }
    if (role === "auditor") {
      result.snapshot.patient = { name: "受限", encounterRef: "受限", diagnosis: "受限", dischargeTo: "受限", allergy: "受限" };
      result.risks = [];
      result.taskDraft = null;
      result.tasks = [];
    }
    return result;
  }

  listTasks(role) {
    this.requireRole(role, ["doctor", "nurse", "case_manager"]);
    return copy(this.tasks.filter((task) => role === "doctor" || task.assigneeRole === role));
  }
}
