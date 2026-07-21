# 臻护 · 前端组件-API-端点 三元映射表

> 臻护 v2.0 | 当前前端页面、Service 与推荐接口映射 | 全栈 / QA / 排障

> **当前校准**：路由与运行端口以 [臻护-代码现状基线.md](臻护-代码现状基线.md) 为准。表中列的是前端主调用链，不把 OpenAPI 的 `/v1/*` 兼容别名重复计入。

---

## 一、页面级映射

| 页面 | 路由 | 调用 Service | 调用 Hook | 关键后端端点 |
|------|------|------|------|------|
| HomePage | `/` | assistant-service | — | GET /assistant/public/quick-questions |
| LoginPage | `/login` | auth-service | auth-store | GET /inpatient/whoami, POST /inpatient/login |
| WorkbenchPage | `/department/:department/doctor`（兼容 `/workbench`） | ward-service, review-service, alert-service | use-ward | GET /ward/pending, /ward/patients, /ward/workspace/alerts, /ward/overview, /ward/priority, /ward/visit-order, POST /inpatient/review/{id} |
| DashboardPage | `/patient/:id` | patient-service, assistant-service, alert-service, evidence-service, agent-flow-service, clinical-brief-service, follow-up-service | use-patient-dashboard | GET /inpatient/{id}/dashboard, /scores, /vital-trends, /lab-trends, /rounds, /nursing, /clinical-note, /evidence, /evidence-graph, /clinical-brief, /agent-flow, /follow-up-contacts, /care-management, POST /rounds/generate, PATCH /rounds/{n}/edit, POST /rounds/{n}/review, /command, /query |
| DischargePage | `/patient/:id/discharge` | patient-service, education-service, evidence-service, follow-up-service, alert-service | — | GET /inpatient/{id}/discharge-summary, POST /inpatient/discharge/{id}, /acknowledge-handoff, /care/education-records, POST /inpatient/review/{id} (type=discharge_sign) |
| NurseBoardPage | `/department/:department/nurse`（兼容 `/nurse`） | nurse-management-service, ward-service, alert-service | use-nurse-management | GET /nurse/tasks, /ai-priority, /department-checklist, POST /nurse/tasks/{id}/complete, GET /monitoring/overdue, /ward/shift-report |
| AdminPage | `/department/:department/management`（兼容 `/admin`） | admin-service, nurse-management-service, ward-service | use-admin | GET /inpatient/admin-capabilities, /admin/rag/dashboard, /admin/rag/entries（`search/layer/page/page_size`）, /admin/rag/preview（`query/layers/top_k`）, /admin/evidence-graph/*, /inpatient/org, /inpatient/templates, /inpatient/db-stats；管理者写操作与演示患者重置见下表 |

---

## 二、组件级映射

### 2.1 布局组件 (4)

| 组件 | Service | Hook | 端点 |
|------|------|------|------|
| AppShell | auth-service | auth-store | — |
| TopBar | auth-service | auth-store | GET /inpatient/whoami |
| LeftNav | auth-service | auth-store (判断 role) | — |
| GlobalAssistantLauncher | assistant-service | — | POST /assistant/chat/stream |

### 2.2 临床组件 (25)

| 组件 | Service | Hook | 端点 |
|------|------|------|------|
| PatientAssistantPanel | assistant-service (22) | — | POST /assistant/chat/stream, /assistant/chat, GET /assistant/quick-questions, /assistant/sessions, /assistant/session/{id}, POST /assistant/session/{id}/reset |
| DiffPanel | review-service, evidence-service | — | POST /inpatient/review/{id}, GET /inpatient/{id}/evidence |
| CareManagementPanel | patient-service | — | GET /inpatient/{id}/care-management, POST /care/medication-orders, PATCH /care/medication-orders/{oid}, POST /care/mdt-requests, POST /care/education-records, POST /care/follow-up-tasks, PATCH /care/follow-up-tasks/{tid} |
| WardClinicalBoard | ward-service | use-ward | GET /ward/overview, /ward/patients, /ward/pending |
| NursePatientDrawer | patient-service, nurse-management-service | — | GET /inpatient/{id}/dashboard, GET /nurse/tasks |
| ClinicalMonitoringEntryPanel | patient-service | — | POST /inpatient/monitoring/{id}/vitals, POST /inpatient/monitoring/{id}/labs |
| NurseWorkspacePanels | nurse-management-service, ward-service | use-nurse-management | GET /nurse/tasks, /nurse/ai-priority, /ward/shift-report, /monitoring/overdue |
| NursingTaskCompletionDialog | nurse-management-service | — | POST /nurse/tasks/{id}/complete |
| NursePatientDirectoryPanel | patient-directory-service | use-patient-directory | GET /patients |
| DischargeEducationPanel | education-service, patient-service | — | POST /inpatient/{id}/care/education-records, GET /inpatient/rag/search?layer=L9 |
| CommandBar | patient-service | — | POST /inpatient/{id}/command, POST /inpatient/discharge/{id} |
| MedicationSafetyPanel | patient-service | — | 使用 dashboard.medication_safety (由 GET /inpatient/{id}/dashboard 返回) |
| EvidenceGraphPathPanel | evidence-service | — | GET /inpatient/{id}/evidence-graph |
| EvidencePanel | evidence-service | — | GET /inpatient/{id}/evidence |
| FollowUpOverviewPanel | follow-up-service | use-follow-up | GET /inpatient/{id}/follow-up-contacts |
| ClinicalBriefPanel | clinical-brief-service | — | GET /inpatient/{id}/clinical-brief |
| AgentFlowPanel | agent-flow-service | — | GET /inpatient/{id}/agent-flow |
| NursingRecordsPanel | patient-service | — | GET /inpatient/{id}/nursing |
| AlertLifecyclePanel | alert-service | — | GET /inpatient/{id}/alerts, POST /inpatient/{id}/alerts/{alert_id}/acknowledge, POST /inpatient/{id}/alerts/{alert_id}/resolve |
| ClinicalIntakePanel | patient-service | — | GET /inpatient/{id}/dashboard |
| PatientClinicalQueryPanel | patient-service | — | POST /inpatient/{id}/query |
| NursingEntryDialog | patient-service | — | POST /inpatient/admissions/{id}/nursing |
| FollowUpContactPanel | patient-service | — | 读写 follow_up_contacts (encrypted) |
| PatientDirectoryPanel | patient-directory-service | use-patient-directory | GET /patients |
| DischargeWorkflowPanel | patient-service | — | GET /inpatient/{id}/discharge-summary, POST /inpatient/discharge/{id}/acknowledge-handoff |
| RoundsManagementPanel | patient-service | — | GET /inpatient/{id}/rounds, POST /rounds/generate, PATCH /rounds/{n}/edit, POST /rounds/{n}/review |
| AdmissionLauncher | patient-service | — | POST /inpatient/admissions |

### 2.3 管理组件 (5)

| 组件 | Service | Hook | 端点 |
|------|------|------|------|
| AdminDataPanels | admin-service | use-admin | GET /inpatient/admin-capabilities, /admin/rag/dashboard, /admin/rag/entries, /admin/rag/preview, /inpatient/org, /inpatient/db-stats |
| EvidenceGraphPanel | admin-service | use-admin | GET /admin/evidence-graph/status, /diseases/{id}, /diseases/{id}/visualization；POST /admin/evidence-graph/rebuild |
| NurseManagementPanel | nurse-management-service, ward-service | use-nurse-management | GET /nurse/kpi, /nurse/tasks, /nurse/ai-priority, /ward/shift-report, /nurse/department-checklist |
| SystemOperationsPanel | admin-service | — | GET /inpatient/admin-capabilities 后按 capability 调用 POST /admin/rag/reindex, /admin/evidence-graph/rebuild, /inpatient/seed-all, /inpatient/org/seed, /inpatient/clear-expired；仅开发/演示环境且 `demo_patient_reset` 可用时调用 POST /inpatient/fixtures/reset-demo（`confirmed=true,purge_runtime=true`） |
| DiseaseTemplatePanel | admin-service | — | GET /inpatient/templates |

---

## 三、Service → 端点 全量对照

| Service 文件 | 导出 | 调用端点 |
|------|:--:|------|
| patient-service.ts | 当前导出以源码为准 | /inpatient/{id}/dashboard, /scores, /vital-trends, /lab-trends, /rounds（读取/生成/编辑/核对）, /nursing, /clinical-note, /evidence, /command, /query, /care-management, /care/medication-orders, /care/mdt-requests, /care/education-records, /care/follow-up-tasks, /discharge/{id}, /discharge-summary, /admissions, /admissions/{id}/history, /admissions/{id}/physical-exam, /admissions/{id}/nursing, /monitoring/{id}/vitals, /monitoring/{id}/labs, /assistant-action-drafts, /clinical-brief, /evidence-graph, /agent-flow, /follow-up-contact(s), /discharge/{id}/acknowledge-handoff |
| ward-service.ts | 12 | /ward/pending, /ward/patients, /ward/workspace/alerts, /ward/overview, /ward/alerts, /ward/vitals, /ward/trends, /ward/lab-summary, /ward/workload, /ward/ai-summary, /ward/visit-order, /ward/priority |
| assistant-service.ts | 22 | /assistant/chat, /assistant/chat/stream, /assistant/public/chat/stream, /assistant/quick-questions, /assistant/public/quick-questions, /assistant/sessions, /assistant/session/{id}, /assistant/session/{id}/reset, /inpatient/{id}/assistant-action-drafts (6 个 CRUD) |
| admin-service.ts | 当前导出以源码为准 | /inpatient/admin-capabilities, /admin/rag/dashboard, /admin/rag/entries, /admin/rag/preview, /admin/rag/reindex, /admin/rag/diagnostics, /admin/rag/maintenance-log, /admin/evidence-graph/*, /inpatient/org, /inpatient/org/seed, /inpatient/seed-all, /inpatient/clear-expired, /inpatient/fixtures/reset-demo, /inpatient/templates, /inpatient/db-stats |
| nurse-management-service.ts | 7 | /nurse/tasks, /nurse/tasks/{id}/complete, /nurse/ai-priority, /nurse/department-checklist, /nurse/kpi, /monitoring/overdue, /ward/shift-report |
| alert-service.ts | 4 | /inpatient/{id}/alerts, /inpatient/{id}/alerts/{alert_id}/acknowledge, /inpatient/{id}/alerts/{alert_id}/resolve |
| auth-service.ts | 3 | /inpatient/whoami, /inpatient/login |
| education-service.ts | 3 | /inpatient/rag/search?layer=L9, education resources |
| evidence-service.ts | 3 | /inpatient/{id}/evidence, /inpatient/{id}/evidence-graph |
| agent-flow-service.ts | 7 | /inpatient/{id}/agent-flow |
| clinical-brief-service.ts | 5 | /inpatient/{id}/clinical-brief |
| follow-up-service.ts | 1 | /inpatient/{id}/follow-up-contacts |
| patient-directory-service.ts | 1 | /patients |
| review-service.ts | 1 | /inpatient/review/{id} |

---

> 文档版本 v2.0 · 当前前端主调用链 · 2026-07-21 · 兼容路径与完整操作数见代码现状基线
