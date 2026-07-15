const CASE_ID = "CASE-2026-0715-0042";
const API_ROOT = "/api/v1";
let overview = null;
let selectedRiskId = null;
let demoRole = "doctor";
let knowledgeDocuments = [];
let ingestionJobs = [];

const elements = {
  riskList: document.querySelector("#risk-list"),
  riskTotal: document.querySelector("#risk-total"),
  riskTemplate: document.querySelector("#risk-template"),
  progress: document.querySelector("#review-progress"),
  caseState: document.querySelector("#case-state-text"),
  caseDot: document.querySelector("#case-state-dot"),
  draftStatus: document.querySelector("#draft-status"),
  draftEmpty: document.querySelector("#draft-empty"),
  draftContent: document.querySelector("#draft-content"),
  publishButton: document.querySelector("#publish-button"),
  taskCount: document.querySelector("#task-count"),
  taskEmpty: document.querySelector("#task-empty"),
  taskList: document.querySelector("#task-list"),
  auditList: document.querySelector("#audit-list"),
  auditCount: document.querySelector("#audit-count"),
  rolePicker: document.querySelector("#demo-role"),
  scenarioPicker: document.querySelector("#demo-scenario"),
  loadScenario: document.querySelector("#load-scenario"),
  serviceState: document.querySelector("#service-state"),
  notice: document.querySelector(".notice"),
  noticeText: document.querySelector("#notice-text"),
  knowledgeQuery: document.querySelector("#knowledge-query"),
  knowledgeSearchButton: document.querySelector("#knowledge-search-button"),
  knowledgeResults: document.querySelector("#knowledge-results"),
  knowledgeDocuments: document.querySelector("#knowledge-documents"),
  knowledgeImportForm: document.querySelector("#knowledge-import-form"),
  knowledgeFile: document.querySelector("#knowledge-file"),
  knowledgeResetButton: document.querySelector("#knowledge-reset-button"),
  ingestionJobsPanel: document.querySelector("#ingestion-jobs-panel"),
  ingestionJobs: document.querySelector("#ingestion-jobs"),
  ingestionJobCount: document.querySelector("#ingestion-job-count"),
  pageHeading: document.querySelector(".page-heading"),
  scenarioBar: document.querySelector(".scenario-bar"),
  profileAvatar: document.querySelector(".profile .avatar"),
  profileName: document.querySelector(".profile strong"),
  profileRole: document.querySelector(".profile span"),
  breadcrumbRoot: document.querySelector(".breadcrumb span"),
  breadcrumbCurrent: document.querySelector(".breadcrumb strong"),
  editDialog: document.querySelector("#edit-dialog"),
  editTitle: document.querySelector("#edit-title"),
  editNote: document.querySelector("#edit-note"),
  editForm: document.querySelector("#edit-form"),
  supplementDialog: document.querySelector("#supplement-dialog"),
  supplementTitle: document.querySelector("#supplement-title"),
  supplementResult: document.querySelector("#supplement-result"),
  supplementNote: document.querySelector("#supplement-note"),
  supplementForm: document.querySelector("#supplement-form")
};

const statusLabel = {
  draft: "新建",
  analysing: "分析中",
  review_pending: "待医生审核",
  confirmed: "已确认（待生成草稿）",
  rejected: "已驳回（待生成草稿）",
  task_draft: "任务草稿就绪",
  simulated_published: "已模拟发布",
  knowledge_changed: "知识已变化 · 已阻断",
  closed: "已关闭",
  cancelled: "已取消",
  failed: "分析失败，待人工处理"
};

const knowledgeStatusLabel = {
  review_pending: "待审核",
  published: "已发布",
  expired: "已过期",
  withdrawn: "已撤回",
  superseded: "已替代",
  archived: "已归档",
  review_rejected: "审核驳回"
};

const ingestionStatusLabel = {
  queued: "排队中",
  parsing: "解析中",
  review_pending: "待审核",
  failed: "失败"
};

const roleProfile = {
  doctor: { name: "周医生", role: "心内科 · 经治医生", avatar: "周" },
  nurse: { name: "护理随访", role: "模拟角色 · 只读待办", avatar: "护" },
  auditor: { name: "审计员", role: "模拟角色 · 审计查阅", avatar: "审" },
  knowledge_admin: { name: "知识管理员", role: "模拟角色 · 知识库审核", avatar: "知" }
};

const sourceMimeByFormat = {
  txt: "text/plain",
  md: "text/markdown",
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
};

function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Demo-Role": demoRole,
    "X-Use-Purpose": "poc-review",
    "X-Request-Id": crypto.randomUUID(),
    ...options.headers
  };
  return fetch(`${API_ROOT}${path}`, { ...options, headers }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok) throw new Error(`${payload.error.code}: ${payload.error.message}`);
    return payload.data;
  });
}

function statusText(status) {
  return { pending: "待审核", confirmed: "已确认", rejected: "已驳回", escalated: "已升级" }[status];
}

function renderRisks() {
  elements.riskList.replaceChildren();
  elements.riskTotal.textContent = String(overview.risks.length);
  if (!overview.risks.length) {
    elements.riskList.innerHTML = `<div class="empty-state">当前角色无待审核项，或此场景未生成可审核风险。</div>`;
    return;
  }
  overview.risks.forEach((risk) => {
    const card = elements.riskTemplate.content.firstElementChild.cloneNode(true);
    card.dataset.status = risk.status;
    const severity = card.querySelector(".severity");
    severity.textContent = risk.severityLabel;
    severity.classList.add(risk.severityClass);
    card.querySelector(".risk-type").textContent = risk.type;
    const sourceTag = document.createElement("span");
    sourceTag.className = "source-tag";
    sourceTag.textContent = { source_ehr: "EHR", source_knowledge: "知识", source_hybrid: "混合" }[risk.evidence.source_type] || "";
    card.querySelector(".risk-type").insertAdjacentElement("afterend", sourceTag);
    const status = card.querySelector(".risk-status");
    status.textContent = statusText(risk.status);
    status.classList.add(risk.status);
    card.querySelector("h3").textContent = risk.title;
    card.querySelector(".risk-summary").textContent = risk.decision?.note ? `${risk.summary} 审核说明：${risk.decision.note}` : risk.summary;
    const evidence = card.querySelector(".evidence-button");
    evidence.textContent = risk.evidence.label;
    evidence.addEventListener("click", () => showEvidence(risk, "输入证据"));
    const citation = card.querySelector(".guideline-button");
    citation.textContent = risk.citation.label;
    citation.addEventListener("click", () => showEvidence(risk, "知识来源"));
    const isPending = risk.status === "pending" && demoRole === "doctor";
    card.querySelector(".confirm-button").disabled = !isPending;
    card.querySelector(".reject-button").disabled = !isPending;
    card.querySelector(".edit-button").disabled = !isPending;
    card.querySelector(".confirm-button").addEventListener("click", () => reviewRisk(risk, "confirm"));
    card.querySelector(".reject-button").addEventListener("click", () => reviewRisk(risk, "reject"));
    card.querySelector(".edit-button").addEventListener("click", () => openEdit(risk));
    const escalateButton = document.createElement("button");
    escalateButton.type = "button";
    escalateButton.className = "secondary-button escalate-button";
    escalateButton.textContent = "升级";
    escalateButton.disabled = !isPending;
    escalateButton.addEventListener("click", () => reviewRisk(risk, "escalate", prompt("升级原因") || ""));
    card.querySelector(".edit-button").parentNode.appendChild(escalateButton);
    if (risk.status === "escalated") {
      card.querySelector(".confirm-button").disabled = true;
      card.querySelector(".reject-button").disabled = true;
      card.querySelector(".edit-button").disabled = true;
      escalateButton.disabled = true;
    }
    elements.riskList.append(card);
  });
}

function renderWorkflow() {
  const handled = overview.risks.filter((risk) => risk.status !== "pending").length;
  const state = overview.case.state;
  elements.progress.textContent = `${handled} / ${overview.risks.length} 已处理`;
  elements.caseState.textContent = statusLabel[state] ?? state;
  elements.caseDot.className = `state-dot${state === "task_draft" ? " draft" : state === "simulated_published" ? " published" : state === "knowledge_changed" ? " blocked" : ""}`;
  const canAct = demoRole === "doctor";
  elements.publishButton.disabled = !canAct;

  if (state === "failed") {
    elements.draftStatus.textContent = "明确降级";
    elements.draftStatus.className = "status-pill muted";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftEmpty.innerHTML = `<div class="empty-icon">!</div><p>分析依赖或知识版本不可用，未生成风险项和任务草稿。</p>`;
    elements.draftContent.classList.add("hidden");
    elements.publishButton.textContent = "当前场景不可发布";
    elements.publishButton.disabled = true;
    return;
  }

  if (!canAct) {
    elements.draftStatus.textContent = "只读视图";
    elements.draftStatus.className = "status-pill muted";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftEmpty.innerHTML = `<div class="empty-icon">·</div><p>当前角色不能审核风险或生成任务草稿。</p>`;
    elements.draftContent.classList.add("hidden");
    elements.publishButton.textContent = "当前角色不可操作";
    elements.publishButton.disabled = true;
    return;
  }

  if (state === "review_pending" && handled < overview.risks.length) {
    elements.draftStatus.textContent = "等待审核";
    elements.draftStatus.className = "status-pill muted";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftContent.classList.add("hidden");
    elements.publishButton.textContent = "完成全部审核后生成草稿";
    elements.publishButton.disabled = true;
    return;
  }
  if (state === "confirmed" || state === "rejected") {
    elements.draftStatus.textContent = "可生成草稿";
    elements.draftStatus.className = "status-pill ready";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftContent.classList.add("hidden");
    elements.publishButton.textContent = "生成任务草稿";
    elements.publishButton.disabled = !canAct;
    return;
  }
  if (state === "task_draft") {
    renderDraft();
    elements.draftStatus.textContent = "草稿就绪";
    elements.draftStatus.className = "status-pill ready";
    elements.publishButton.textContent = "模拟发布至待办";
    elements.publishButton.disabled = !canAct;
    return;
  }
  if (state === "simulated_published") {
    renderDraft();
    elements.draftStatus.textContent = "已模拟发布";
    elements.draftStatus.className = "status-pill published";
    elements.publishButton.textContent = "关闭病例协同";
    elements.publishButton.disabled = !canAct;
    return;
  }

  if (state === "knowledge_changed") {
    elements.draftStatus.textContent = "知识已变化 · 已阻断发布";
    elements.draftStatus.className = "status-pill muted";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftContent.classList.add("hidden");
    elements.draftEmpty.innerHTML = `<div class="empty-icon">!</div><p>所引用知识已过期/撤回/被替代，病例已被阻断，须重新检索与人工复核后才能生成草稿。</p>`;
    elements.publishButton.textContent = "重新核实";
    elements.publishButton.disabled = !canAct;
    return;
  }

  if (state === "closed" || state === "cancelled") {
    elements.draftStatus.textContent = state === "closed" ? "已关闭" : "已取消";
    elements.draftStatus.className = "status-pill muted";
    elements.draftEmpty.classList.remove("hidden");
    elements.draftContent.classList.add("hidden");
    elements.draftEmpty.innerHTML = `<div class="empty-icon">·</div><p>本病例协同已${state === "closed" ? "关闭" : "取消"}。</p>`;
    elements.publishButton.textContent = "已结束";
    elements.publishButton.disabled = true;
  }
}

function renderDraft() {
  elements.draftEmpty.classList.add("hidden");
  elements.draftContent.classList.remove("hidden");
  elements.draftContent.innerHTML = `<h3>计划生成 ${overview.taskDraft.tasks.length} 个模拟任务</h3><ul>${overview.taskDraft.tasks.map((task) => `<li>${task.assigneeRole === "nurse" ? "护理随访" : "个案管理"}：${task.title}</li>`).join("")}</ul>`;
}

function renderPatient() {
  const data = overview.snapshot.patient;
  document.querySelector(".patient-data").innerHTML = `
    <div><dt>姓名</dt><dd>${data.name} <span>已脱敏</span></dd></div>
    <div><dt>住院号</dt><dd>${data.encounterRef}</dd></div>
    <div><dt>主要诊断</dt><dd>${data.diagnosis}</dd></div>
    <div><dt>出院去向</dt><dd>${data.dischargeTo}</dd></div>
    <div><dt>过敏史</dt><dd>${data.allergy}</dd></div>`;
}

function renderTasks() {
  elements.taskCount.textContent = String(overview.tasks.length);
  elements.taskList.replaceChildren();
  if (!overview.tasks.length) {
    elements.taskEmpty.classList.remove("hidden");
    elements.taskList.classList.add("hidden");
    return;
  }
  elements.taskEmpty.classList.add("hidden");
  elements.taskList.classList.remove("hidden");
  overview.tasks.forEach((task, index) => {
    const row = document.createElement("article");
    row.className = "task-row";
    const canSupplement = task.assigneeRole === demoRole && task.status === "simulated_pending";
    const resultText = task.executionResult ? ` · 执行：${task.executionResult.result || "（已补充）"}` : "";
    row.innerHTML = `<span class="task-number">${index + 1}</span><div><strong>${task.title}</strong><span>接收角色：${task.assigneeRole === "nurse" ? "护理随访" : "个案管理"} · 计划完成：${task.due}${resultText}</span></div><span class="task-tag">${task.status === "simulated_supplemented" ? "已补充" : "模拟待办"}</span>`;
    if (canSupplement) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-button task-supplement-button";
      button.textContent = "补充执行";
      button.addEventListener("click", () => openSupplement(task));
      row.children[1].append(button);
    }
    elements.taskList.append(row);
  });
}

let selectedTaskId = null;
function openSupplement(task) {
  selectedTaskId = task.taskId;
  elements.supplementTitle.textContent = `补充执行：${task.title}`;
  elements.supplementResult.value = task.executionResult?.result ?? "";
  elements.supplementNote.value = task.executionResult?.note ?? "";
  elements.supplementDialog.showModal();
  elements.supplementResult.focus();
}

async function submitSupplement(task, result, note) {
  try {
    overview = await api(`/cases/${CASE_ID}/tasks/${task.taskId}/supplement`, { method: "POST", body: JSON.stringify({ result, note }) });
    render();
    setNotice(`<strong>任务执行已补充：</strong>${task.title}。`);
  } catch (error) { window.alert(error.message); }
}

function renderAudit() {
  elements.auditCount.textContent = `${overview.audit.length} 条记录`;
  elements.auditList.replaceChildren();
  overview.audit.forEach((entry) => {
    const row = document.createElement("article");
    row.className = "audit-row";
    const time = new Date(entry.occurredAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    row.innerHTML = `<span class="audit-time">${time}</span><div class="audit-detail"><strong>${entry.title}</strong><span>${entry.detail}</span></div><span class="audit-actor">${entry.actor === "doctor" ? "周医生" : "系统"}</span>`;
    elements.auditList.append(row);
  });
}

function render() {
  renderRisks();
  renderWorkflow();
  renderPatient();
  renderTasks();
  renderAudit();
}

function setNotice(message, type = "default") {
  elements.notice.classList.toggle("error", type === "error");
  elements.noticeText.innerHTML = message;
}

async function refreshHealth() {
  try {
    const response = await fetch("/healthz");
    const health = await response.json();
    if (!response.ok || health.status !== "ok") throw new Error("服务不可用");
    elements.serviceState.className = "service-state healthy";
    elements.serviceState.innerHTML = `<i></i>服务正常 · ${health.workflow_state}`;
  } catch {
    elements.serviceState.className = "service-state unhealthy";
    elements.serviceState.innerHTML = "<i></i>服务不可用";
  }
}

async function refresh() {
  overview = await api(`/cases/${CASE_ID}/overview`);
  render();
  refreshHealth();
}

async function loadScenario() {
  const scenario = elements.scenarioPicker.value;
  try {
    overview = await api("/demo/reset", { method: "POST", body: JSON.stringify({ scenario, interactive: true }) });
    if (overview.case.state === "failed") setNotice(`<strong>明确降级：</strong>${elements.scenarioPicker.options[elements.scenarioPicker.selectedIndex].text}，系统未生成风险项或任务草稿。`, "error");
    else setNotice(`<strong>PoC 场景：</strong>${elements.scenarioPicker.options[elements.scenarioPicker.selectedIndex].text}。数据仅用于验证，不用于真实诊疗。`);
    render();
  } catch (error) {
    await refresh();
    setNotice(`<strong>明确降级：</strong>${error.message}。系统未生成风险项或任务草稿。`, "error");
  }
}

function renderKnowledge() {
  elements.knowledgeDocuments.replaceChildren();
  elements.knowledgeImportForm.classList.toggle("hidden", demoRole !== "knowledge_admin");
  if (!knowledgeDocuments.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "当前角色无权查看知识资产，或没有可见文档。";
    elements.knowledgeDocuments.append(empty);
    return;
  }
  knowledgeDocuments.forEach((knowledgeDocument) => {
    const row = document.createElement("article");
    row.className = "knowledge-document";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = knowledgeDocument.title;
    const detail = document.createElement("span");
    detail.textContent = `版本 ${knowledgeDocument.version} · ${knowledgeDocument.owner} · ${knowledgeDocument.chunkCount} 个分块 · 有效至 ${knowledgeDocument.effectiveUntil}`;
    content.append(title, detail);
    const actions = document.createElement("div");
    actions.className = "knowledge-document-actions";
    const status = document.createElement("span");
    status.className = `status-pill ${knowledgeDocument.available ? "ready" : "muted"}`;
    status.textContent = knowledgeStatusLabel[knowledgeDocument.status] ?? knowledgeDocument.status;
    actions.append(status);
    if (demoRole === "knowledge_admin") {
      knowledgeActions(knowledgeDocument).forEach((action) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary-button knowledge-transition-button";
        button.textContent = action.label;
        button.addEventListener("click", () => transitionKnowledge(knowledgeDocument, action.status));
        actions.append(button);
      });
    }
    row.append(content, actions);
    elements.knowledgeDocuments.append(row);
  });
}

function renderIngestionJobs() {
  const canManage = demoRole === "knowledge_admin";
  elements.ingestionJobsPanel.classList.toggle("hidden", !canManage);
  if (!canManage) return;
  elements.ingestionJobCount.textContent = `${ingestionJobs.length} 条`;
  elements.ingestionJobs.replaceChildren();
  if (!ingestionJobs.length) {
    const empty = document.createElement("div");
    empty.className = "ingestion-job-empty";
    empty.textContent = "当前没有入库任务。";
    elements.ingestionJobs.append(empty);
    return;
  }
  ingestionJobs.forEach((job) => {
    const row = document.createElement("article");
    row.className = "ingestion-job";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = job.title;
    const detail = document.createElement("span");
    const suffix = job.error ? ` · ${job.error.code}` : job.documentId ? ` · ${job.documentId}` : "";
    detail.textContent = `${job.sourceFileName} · ${job.sourceFormat.toUpperCase()} · 第 ${job.attempt} 次${suffix}`;
    content.append(title, detail);
    const actions = document.createElement("div");
    actions.className = "ingestion-job-actions";
    const status = document.createElement("span");
    status.className = `status-pill ${job.status === "failed" ? "failed" : job.status === "review_pending" ? "ready" : "muted"}`;
    status.textContent = ingestionStatusLabel[job.status] ?? job.status;
    actions.append(status);
    if (job.status === "failed" && job.error?.retryable) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "secondary-button knowledge-transition-button";
      retry.textContent = "重试";
      retry.addEventListener("click", () => retryIngestionJob(job));
      actions.append(retry);
    }
    row.append(content, actions);
    elements.ingestionJobs.append(row);
  });
}

function knowledgeActions(document) {
  if (document.status === "review_pending") return [{ status: "published", label: "发布" }, { status: "withdrawn", label: "撤回" }];
  if (document.status === "published") return [{ status: "expired", label: "标记过期" }, { status: "withdrawn", label: "撤回" }];
  return [];
}

async function loadKnowledge() {
  try {
    knowledgeDocuments = await api("/knowledge/documents");
    renderKnowledge();
    await loadIngestionJobs();
  } catch (error) {
    knowledgeDocuments = [];
    renderKnowledge();
    setNotice(`<strong>知识资产访问受限：</strong>${error.message}`, "error");
  }
}

async function loadIngestionJobs() {
  if (demoRole !== "knowledge_admin") {
    ingestionJobs = [];
    renderIngestionJobs();
    return;
  }
  try {
    ingestionJobs = await api("/knowledge/import-jobs");
    renderIngestionJobs();
  } catch (error) {
    ingestionJobs = [];
    renderIngestionJobs();
    setNotice(`<strong>入库任务访问受限：</strong>${error.message}`, "error");
  }
}

async function searchKnowledge() {
  const query = elements.knowledgeQuery.value.trim();
  if (!query) return;
  try {
    const results = await api(`/knowledge/search?q=${encodeURIComponent(query)}`);
    elements.knowledgeResults.classList.remove("hidden");
    elements.knowledgeResults.replaceChildren();
    const heading = document.createElement("h3");
    heading.textContent = `检索结果 ${results.length} 条`;
    elements.knowledgeResults.append(heading);
    if (!results.length) {
      const empty = document.createElement("div");
      empty.className = "knowledge-result";
      empty.textContent = "无可用已发布知识引用。";
      elements.knowledgeResults.append(empty);
    }
    results.forEach((item) => {
      const result = document.createElement("div");
      result.className = "knowledge-result";
      const title = document.createElement("strong");
      title.textContent = item.label;
      const metadata = document.createElement("div");
      metadata.textContent = `${item.location} · ${item.chunkId} · 分数 ${item.score ?? "-"}`;
      const excerpt = document.createElement("div");
      excerpt.textContent = item.excerpt;
      const strategy = document.createElement("span");
      strategy.textContent = `${item.retrievalStrategyVersion}${item.retrieval?.model ? ` · ${item.retrieval.model}` : ""}`;
      result.append(title, metadata, excerpt, strategy);
      elements.knowledgeResults.append(result);
    });
  } catch (error) { setNotice(`<strong>检索失败：</strong>${error.message}`, "error"); }
}

async function transitionKnowledge(knowledgeDocument, status) {
  try {
    const updated = await api(`/knowledge/documents/${encodeURIComponent(knowledgeDocument.documentId)}/transition`, { method: "POST", body: JSON.stringify({ status }) });
    await loadKnowledge();
    setNotice(`<strong>知识状态已更新：</strong>${updated.title} ${knowledgeStatusLabel[updated.status]}。${updated.available ? "该版本已进入检索索引。" : "该版本不参与检索。"}`);
  } catch (error) { setNotice(`<strong>知识状态更新失败：</strong>${error.message}`, "error"); }
}

async function importKnowledge(event) {
  event.preventDefault();
  const file = elements.knowledgeFile.files[0];
  if (!file) return;
  const extension = file.name.split(".").pop().toLowerCase();
  if (!Object.hasOwn(sourceMimeByFormat, extension)) {
    setNotice("<strong>导入失败：</strong>PoC 仅支持 .txt、.md、.pdf 和 .docx 文件。", "error");
    return;
  }
  if (!file.size || file.size > 5 * 1024 * 1024) {
    setNotice("<strong>导入失败：</strong>来源文件大小必须在 1 字节到 5 MiB 之间。", "error");
    return;
  }
  try {
    const form = new FormData(elements.knowledgeImportForm);
    const source = extension === "txt" || extension === "md"
      ? { content: await file.text() }
      : { fileBase64: await fileAsBase64(file) };
    const job = await api("/knowledge/documents/import", {
      method: "POST",
      body: JSON.stringify({
        title: form.get("title"), version: form.get("version"), owner: form.get("owner"),
        effectiveFrom: form.get("effectiveFrom"), effectiveUntil: form.get("effectiveUntil"),
        sourceFileName: file.name, sourceFormat: extension, sourceMime: file.type || sourceMimeByFormat[extension], ...source
      })
    });
    elements.knowledgeImportForm.reset();
    await loadIngestionJobs();
    const completed = await waitForIngestionJob(job.jobId);
    if (completed.status === "review_pending") setNotice(`<strong>已导入待审核：</strong>${completed.title} 已完成解析，发布前不会参与检索。`);
    else setNotice(`<strong>知识入库失败：</strong>${completed.error.code}: ${completed.error.message}`, "error");
  } catch (error) { setNotice(`<strong>知识导入失败：</strong>${error.message}`, "error"); }
}

async function fileAsBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const parts = [];
  for (let offset = 0; offset < bytes.length; offset += 8192) parts.push(String.fromCharCode(...bytes.subarray(offset, offset + 8192)));
  return btoa(parts.join(""));
}

async function waitForIngestionJob(jobId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 100));
    const job = await api(`/knowledge/import-jobs/${encodeURIComponent(jobId)}`);
    if (["review_pending", "failed"].includes(job.status)) {
      await loadKnowledge();
      return job;
    }
    await loadIngestionJobs();
  }
  throw new Error("知识入库任务等待超时；请在任务队列中查看状态");
}

async function retryIngestionJob(job) {
  try {
    const queued = await api(`/knowledge/import-jobs/${encodeURIComponent(job.jobId)}/retry`, { method: "POST", body: "{}" });
    await loadIngestionJobs();
    const completed = await waitForIngestionJob(queued.jobId);
    setNotice(completed.status === "review_pending" ? `<strong>知识入库已恢复：</strong>${completed.title} 已完成解析并进入待审核。` : `<strong>知识入库仍失败：</strong>${completed.error.code}: ${completed.error.message}`, completed.status === "failed" ? "error" : "default");
  } catch (error) { setNotice(`<strong>知识入库重试失败：</strong>${error.message}`, "error"); }
}

async function resetKnowledgeRuntime() {
  if (!window.confirm("恢复后将清空当前 PoC 的导入文档、入库任务和知识审计记录，并回到预置样例。是否继续？")) return;
  try {
    const reset = await api("/knowledge/runtime/reset", { method: "POST", body: "{}" });
    elements.knowledgeResults.classList.add("hidden");
    elements.knowledgeResults.replaceChildren();
    elements.knowledgeImportForm.reset();
    await loadKnowledge();
    setNotice(`<strong>已恢复预置样例：</strong>当前共有 ${reset.documentCount} 份预置知识文档，入库任务已清空。`);
  } catch (error) { setNotice(`<strong>恢复预置样例失败：</strong>${error.message}`, "error"); }
}

async function reviewRisk(risk, action, note = "", reason = "") {
  try {
    overview = await api(`/cases/${CASE_ID}/risks/${risk.riskId}/review`, { method: "POST", body: JSON.stringify({ action, note, reason }) });
    render();
  } catch (error) { window.alert(error.message); }
}

function openEdit(risk) {
  selectedRiskId = risk.riskId;
  elements.editTitle.textContent = `编辑并确认：${risk.title}`;
  elements.editNote.value = risk.decision?.note ?? "";
  elements.editDialog.showModal();
  elements.editNote.focus();
}

function showEvidence(risk, type) {
  const source = type === "输入证据" ? risk.evidence : risk.citation;
  const detail = type === "输入证据" ? `${source.resourceType} / ${source.resourceRef}\n字段：${source.fieldPath}\n片段：${source.snippet}` : `${source.documentId}\n版本：${source.version}\n定位：${source.location}\n原文：${source.excerpt}`;
  window.alert(`${type}\n\n${detail}\n\n该引用来自服务端预置模拟数据；不访问真实患者或知识库。`);
}

async function primaryAction() {
  try {
    const state = overview.case.state;
    if (state === "review_pending" || state === "confirmed" || state === "rejected") {
      overview = await api(`/cases/${CASE_ID}/task-drafts`, { method: "POST", body: "{}" });
    } else if (state === "task_draft") {
      overview = await api(`/cases/${CASE_ID}/task-drafts/${overview.taskDraft.draftId}/simulated-publish`, { method: "POST", body: "{}" });
    } else if (state === "simulated_published") {
      overview = await api(`/cases/${CASE_ID}/close`, { method: "POST", body: "{}" });
    } else if (state === "knowledge_changed") {
      overview = await api(`/cases/${CASE_ID}/reconcile`, { method: "POST", body: "{}" });
    }
    render();
  } catch (error) { window.alert(error.message); }
}

function switchSection(section) {
  if (demoRole === "knowledge_admin" && section !== "knowledge") {
    section = "knowledge";
    setNotice("<strong>访问范围：</strong>知识管理员仅可访问知识资产和其生命周期记录，不读取模拟病例。", "default");
  }
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.section === section));
  document.querySelectorAll("main section[id]").forEach((item) => item.classList.toggle("hidden", item.id !== section));
  if (section === "knowledge") loadKnowledge();
}

document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => switchSection(item.dataset.section)));
document.querySelector("#publish-button").addEventListener("click", primaryAction);
elements.knowledgeSearchButton.addEventListener("click", searchKnowledge);
elements.knowledgeQuery.addEventListener("keydown", (event) => { if (event.key === "Enter") searchKnowledge(); });
elements.knowledgeImportForm.addEventListener("submit", importKnowledge);
elements.knowledgeResetButton.addEventListener("click", resetKnowledgeRuntime);
elements.loadScenario.addEventListener("click", loadScenario);
elements.rolePicker.addEventListener("change", async () => {
  demoRole = elements.rolePicker.value;
  const profile = roleProfile[demoRole];
  elements.profileAvatar.textContent = profile.avatar;
  elements.profileName.textContent = profile.name;
  elements.profileRole.textContent = profile.role;
  elements.pageHeading.classList.toggle("hidden", demoRole === "knowledge_admin");
  elements.scenarioBar.classList.toggle("hidden", demoRole === "knowledge_admin");
  elements.breadcrumbRoot.textContent = demoRole === "knowledge_admin" ? "知识资产" : "交接工作台";
  elements.breadcrumbCurrent.textContent = demoRole === "knowledge_admin" ? "受控入库审核" : "病例审核";
  try {
    if (demoRole === "knowledge_admin") {
      overview = null;
      switchSection("knowledge");
      setNotice("<strong>当前模拟角色：</strong>知识管理员。仅可导入、发布和管理知识资产；不读取模拟病例。", "default");
      return;
    }
    await refresh();
    setNotice(`<strong>当前模拟角色：</strong>${elements.rolePicker.options[elements.rolePicker.selectedIndex].text}。界面动作与服务端权限共同生效。`);
  } catch (error) { setNotice(`<strong>角色切换失败：</strong>${error.message}`, "error"); }
});
document.querySelector("#show-all-risks").addEventListener("click", () => document.querySelector("#risk-list").scrollIntoView({ behavior: "smooth", block: "start" }));
document.querySelector("#show-snapshot").addEventListener("click", () => window.alert(`输入快照 ${overview.snapshot.snapshotId}\n\n来源：${overview.snapshot.source}\n映射版本：${overview.snapshot.mappingVersion}\n采集时间：${overview.snapshot.capturedAt}\n\n仅保留最小必要字段；不连接 HIS/EMR/LIS。`));
elements.editForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const risk = overview.risks.find((item) => item.riskId === selectedRiskId);
  elements.editDialog.close();
  reviewRisk(risk, "edit_confirm", elements.editNote.value.trim() || "已人工核实，补充说明待后续完善");
});
elements.supplementForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const task = overview.tasks.find((item) => item.taskId === selectedTaskId);
  elements.supplementDialog.close();
  submitSupplement(task, elements.supplementResult.value.trim(), elements.supplementNote.value.trim());
});
document.querySelector("#export-audit").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ case_id: CASE_ID, audit: overview.audit }, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${CASE_ID}-audit-demo.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});

refresh().catch((error) => {
  elements.riskList.innerHTML = `<div class="empty-state">无法加载 PoC 服务：${error.message}</div>`;
});
