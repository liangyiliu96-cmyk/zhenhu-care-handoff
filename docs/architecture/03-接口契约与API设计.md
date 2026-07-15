# 接口契约与 API 设计 v0.2

**状态：** 正式工程基线，基于 `schemas.py`/`routes/cases.py` 现有实现扩展。
**覆盖：** workflow-engine（9 端点）+ knowledge-orchestrator（7 端点）+ fhir-adapter（4 端点）

---

## 1. 统一规范

### 1.1 响应包装

```json
{
  "request_id": "uuid",
  "data": { },
  "error": { "code": "ERROR_CODE", "message": "描述" }
}
```

- `data` 与 `error` 互斥：成功时 `error=null`，失败时 `data=null`
- `request_id` 透传自 `X-Request-ID` 头

### 1.2 HTTP 状态码映射

| 状态码 | 语义 | 触发条件 |
|---|---|---|
| 200 | 成功 | GET/POST 查询型 |
| 201 | 已创建 | POST 创建型（如 `POST /cases`） |
| 400 | 请求参数错误 | Pydantic 校验失败 |
| 403 | 无权访问 | 角色不匹配（`assert_role_access` 失败） |
| 404 | 资源不存在 | case_id / risk_id / document_id 未找到 |
| 409 | 状态冲突 | 状态机拒绝转移（`ILLEGAL_TRANSITION`） |
| 422 | 业务校验失败 | 文件格式/大小/摘要不合法 |
| 500 | 内部错误 | 未预期异常 |

### 1.3 错误码枚举

| 错误码 | HTTP | 说明 | 来源 |
|---|---|---|---|
| `ILLEGAL_TRANSITION` | 409 | 状态转移不合法 | `state_machine.py` |
| `CASE_STATE_CONFLICT` | 409 | 当前状态不允许该操作 | `routes/cases.py` |
| `CASE_NOT_FOUND` | 404 | case_id 不存在 | `routes/cases.py` |
| `RISK_NOT_FOUND` | 404 | risk_id 不存在 | `routes/cases.py` |
| `RISK_ALREADY_REVIEWED` | 409 | 该风险项已完成审核 | `routes/cases.py` |
| `KNOWLEDGE_CHANGED` | 409 | 知识变更阻断：需 reconcile | 需求 §4.4 |
| `FORBIDDEN` | 403 | 角色无权限 | `contracts/__init__.py` |
| `DOCUMENT_NOT_FOUND` | 404 | 知识文档不存在 | — |
| `INGESTION_VALIDATION_FAILED` | 422 | 文件校验失败（类型/大小/签名） | 需求 §4.2 |
| `PATIENT_NOT_FOUND` | 404 | 患者 FHIR 资源不存在 | — |
| `INTERNAL_ERROR` | 500 | 内部异常 | — |

---

## 2. workflow-engine 端点

**Base path:** `POST /cases`（路由前缀 `/cases`，已在 `routes/cases.py` 实现）

### 2.1 POST /cases

| 项 | 值 |
|---|---|
| 状态码 | 201 |
| 鉴权 | doctor / case_manager |

**Request:**
```json
{ "input_snapshot_id": "SNAP-abc123" }
```

**Response (201):**
```json
{
  "request_id": "uuid",
  "data": {
    "case_id": "CASE-a1b2c3d4e5f6",
    "state": "draft",
    "input_snapshot_id": "SNAP-abc123",
    "workflow_version": "0.2.0",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  },
  "error": null
}
```

| 错误码 | 条件 |
|---|---|
| `FORBIDDEN` | 角色无权访问 `case_review` |

### 2.2 POST /cases/{case_id}/analyse

| 项 | 值 |
|---|---|
| 鉴权 | doctor |

**Request:** `{}`（空体）

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "case_id": "CASE-a1b2c3d4e5f6",
    "state": "review_pending",
    "risk_items": [{
      "risk_id": "RISK-x1y2z3",
      "case_id": "CASE-a1b2c3d4e5f6",
      "category": "medication_allergy",
      "severity": "high",
      "severity_label": "高风险",
      "title": "...",
      "summary": "...",
      "status": "pending",
      "decision": null,
      "decision_note": null,
      "evidence_snippet": "...",
      "citation_excerpt": "...",
      "citation_document_id": "drug-label-amoxicillin-clavulanate",
      "created_at": "2025-01-01T00:00:00Z"
    }]
  },
  "error": null
}
```

| 错误码 | 条件 |
|---|---|
| `CASE_NOT_FOUND` | case_id 不存在 |
| `ILLEGAL_TRANSITION` | 当前状态不可分析（如已是 closed/cancelled） |

### 2.3 POST /cases/{case_id}/risks/{risk_id}/review

| 项 | 值 |
|---|---|
| 鉴权 | doctor |

**Request:**
```json
{
  "action": "confirm",
  "note": "已核实，确认风险"
}
```

**Response (200):** 更新后的 `CaseResponse`（同 2.1 data 结构）。

| 错误码 | 条件 |
|---|---|
| `CASE_NOT_FOUND` | case_id 不存在 |
| `RISK_NOT_FOUND` | risk_id 不存在 |
| `RISK_ALREADY_REVIEWED` | 该风险项 status ≠ pending |
| `CASE_STATE_CONFLICT` | case.state ≠ review_pending |
| `FORBIDDEN` | 角色无权 |

### 2.4 POST /cases/{case_id}/task-drafts

| 项 | 值 |
|---|---|
| 鉴权 | doctor / nurse / case_manager |

**Request:** `{}`

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "draft_id": "DRAFT-p9q8r7",
    "case_id": "CASE-a1b2c3d4e5f6",
    "status": "ready",
    "sop_version": "0.2.0",
    "tasks_json": "[{\"task_type\":\"followup\",\"assignee_role\":\"nurse\",\"due\":\"2025-01-15T00:00:00Z\",\"status\":\"simulated_pending\"}]",
    "created_at": "2025-01-01T00:00:00Z"
  },
  "error": null
}
```

| 错误码 | 条件 |
|---|---|
| `CASE_STATE_CONFLICT` | case.state 不在 {confirmed, rejected, review_pending} |
| `FORBIDDEN` | 角色无权 |

### 2.5 POST /cases/{case_id}/task-drafts/{draft_id}/simulated-publish

| 项 | 值 |
|---|---|
| 鉴权 | doctor / case_manager |

**Request:** `{}`

**Response (200):**
```json
{ "request_id": "uuid", "data": { "state": "simulated_published" }, "error": null }
```

| 错误码 | 条件 |
|---|---|
| `KNOWLEDGE_CHANGED` | 所引用知识已变更，阻断发布 |
| `CASE_STATE_CONFLICT` | case.state ≠ task_draft |

### 2.6 POST /cases/{case_id}/close

| 项 | 值 |
|---|---|
| 鉴权 | doctor / case_manager |

**Request:** `{}`

**Response (200):** `{"state": "closed"}`

| 错误码 | 条件 |
|---|---|
| `CASE_STATE_CONFLICT` | case.state ≠ simulated_published |

### 2.7 POST /cases/{case_id}/cancel

| 项 | 值 |
|---|---|
| 鉴权 | doctor / case_manager |

**Request:** `{}`

**Response (200):** `{"state": "cancelled"}`

| 错误码 | 条件 |
|---|---|
| `CASE_STATE_CONFLICT` | case.state ∈ {closed, cancelled}（终态不可取消） |

### 2.8 POST /cases/{case_id}/reconcile

| 项 | 值 |
|---|---|
| 鉴权 | doctor |

**Request:** `{}`

**Response (200):** `{"state": "review_pending"}`

| 错误码 | 条件 |
|---|---|
| `CASE_STATE_CONFLICT` | case.state ≠ knowledge_changed |

### 2.9 POST /cases/{case_id}/tasks/{task_id}/supplement

| 项 | 值 |
|---|---|
| 鉴权 | nurse / case_manager |

**Request:**
```json
{ "result": "已完成首次随访", "note": "患者血压稳定" }
```

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "task_id": "TASK-xxx",
    "status": "simulated_supplemented",
    "execution_result": "已完成首次随访",
    "execution_note": "患者血压稳定"
  },
  "error": null
}
```

| 错误码 | 条件 |
|---|---|
| `FORBIDDEN` | 角色无权（需 nurse / case_manager） |
| `CASE_STATE_CONFLICT` | case.state ≠ simulated_published |
| `CASE_NOT_FOUND` | case_id 不存在 |

---

## 3. knowledge-orchestrator 端点

**Base path:** `/knowledge`

### 3.1 POST /knowledge/documents/import

| 项 | 值 |
|---|---|
| 鉴权 | knowledge_admin |
| Content-Type | multipart/form-data |

**Form 字段：** `file`（.txt/.md/.pdf/.docx, ≤5 MiB）、`title`、`version`、`owner`、`effective_from`、`effective_until`

**Response (201):**
```json
{
  "request_id": "uuid",
  "data": { "job_id": "JOB-xxx", "status": "queued" },
  "error": null
}
```

| 错误码 | 条件 |
|---|---|
| `FORBIDDEN` | 角色非 knowledge_admin |
| `INGESTION_VALIDATION_FAILED` | 文件类型/大小/MIME/签名校验失败 |

### 3.2 GET /knowledge/documents

| 项 | 值 |
|---|---|
| 鉴权 | doctor / auditor / knowledge_admin |

**Query:** `?status=published&page=1&size=20`

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "items": [{ "document_id": "DOC-xxx", "title": "...", "version": "1.0", "status": "published", "owner": "admin", "effective_from": "...", "effective_until": "..." }],
    "total": 42,
    "page": 1,
    "size": 20
  },
  "error": null
}
```

### 3.3 POST /knowledge/documents/{document_id}/transition

| 项 | 值 |
|---|---|
| 鉴权 | knowledge_admin |

**Request:**
```json
{ "next_state": "published" }
```

**Response (200):**
```json
{ "request_id": "uuid", "data": { "document_id": "DOC-xxx", "status": "published" }, "error": null }
```

| 错误码 | 条件 |
|---|---|
| `ILLEGAL_TRANSITION` | 知识状态转移不合法 |
| `DOCUMENT_NOT_FOUND` | document_id 不存在 |

**合法转移：** `review_pending→published/withdrawn/review_rejected`，`published→expired/withdrawn/superseded/archived`

### 3.4 GET /knowledge/search

| 项 | 值 |
|---|---|
| 鉴权 | doctor / auditor / knowledge_admin |

**Query:** `?q=出院药物过敏&filters={"status":"published"}&top_k=10`

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "results": [{
      "chunk_id": "CHUNK-xxx",
      "document_id": "DOC-xxx",
      "text": "...",
      "score": 0.92,
      "location": "§3.2 p12",
      "citation": { "excerpt": "...", "coordinates": "p12:L3-L8" }
    }]
  },
  "error": null
}
```

### 3.5 GET /knowledge/import-jobs

| 项 | 值 |
|---|---|
| 鉴权 | knowledge_admin |

**Query:** `?status=review_pending&page=1&size=20`

**Response (200):** 分页 job 列表（含 `job_id`, `status`, `attempt`, `error`）。

### 3.6 POST /knowledge/runtime/reset

| 项 | 值 |
|---|---|
| 鉴权 | knowledge_admin |

**Request:** `{}`

**Response (200):** `{"status": "reset", "sample_count": 3}`

清除运行时数据，恢复预置样例；不重置 `knowledge_lifecycle_events` 审计记录。

### 3.7 GET /knowledge/audit

| 项 | 值 |
|---|---|
| 鉴权 | auditor / knowledge_admin |

**Query:** `?document_id=DOC-xxx&page=1&size=20`

**Response (200):** 分页 `knowledge_lifecycle_events` 列表。

---

## 4. fhir-adapter 端点

**Base path:** `/fhir`

### 4.1 GET /fhir/Patient/{patient_id}

| 项 | 值 |
|---|---|
| 鉴权 | doctor / nurse / case_manager / auditor |

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "resourceType": "Patient",
    "id": "PAT-xxx",
    "identifier": [{ "value": "TOKEN-xxx" }],
    "name": [{ "text": "TOKEN-xxx" }],
    "gender": "male",
    "birthDate": "1965-04-12"
  },
  "error": null
}
```

所有 PII 字段输出脱敏 token（name→token, identifier→hash）。

| 错误码 | 条件 |
|---|---|
| `PATIENT_NOT_FOUND` | patient_id 不存在 |

### 4.2 GET /fhir/Patient/{patient_id}/CarePlan

| 项 | 值 |
|---|---|
| 鉴权 | doctor / nurse / case_manager |

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "resourceType": "Bundle",
    "entry": [{
      "resource": {
        "resourceType": "CarePlan",
        "id": "CP-xxx",
        "title": "高血压出院随访计划",
        "status": "active",
        "category": [{ "text": "出院随访" }],
        "period": { "start": "2025-01-01", "end": "2025-06-30" }
      }
    }]
  },
  "error": null
}
```

### 4.3 POST /fhir/Consent

| 项 | 值 |
|---|---|
| 鉴权 | doctor / case_manager |

**Request:**
```json
{
  "patient_id": "PAT-xxx",
  "scope": "patient-privacy-consent",
  "status": "active",
  "provision": { "purpose": "出院交接审核" }
}
```

**Response (201):**
```json
{
  "request_id": "uuid",
  "data": { "consent_id": "CON-xxx", "status": "active" },
  "error": null
}
```

### 4.4 GET /fhir/AuditEvent

| 项 | 值 |
|---|---|
| 鉴权 | auditor |

**Query:** `?patient=PAT-xxx&page=1&size=20`

**Response (200):**
```json
{
  "request_id": "uuid",
  "data": {
    "resourceType": "Bundle",
    "entry": [{
      "resource": {
        "resourceType": "AuditEvent",
        "id": "AUDIT-xxx",
        "type": { "code": "R" },
        "entity": [{ "reference": { "reference": "Patient/PAT-xxx" } }],
        "agent": [{ "who": { "display": "doctor" } }],
        "recorded": "2025-01-01T00:00:00Z"
      }
    }]
  },
  "error": null
}
```

---

## 5. 跨服务 Hook

### 5.1 POST /hooks/knowledge-changed（内部）

workflow-engine 暴露，knowledge-orchestrator 在撤回/过期/替代知识后调用。

**Request:**
```json
{
  "document_id": "DOC-xxx",
  "version": "1.0",
  "affected_case_ids": ["CASE-a1b2", "CASE-c3d4"]
}
```

**Response (200):**
```json
{ "blocked_count": 2 }
```

workflow-engine 将受影响病例批量转入 `knowledge_changed` 状态。

---

## 6. 已实现 vs 待实现

| 端点 | 状态 | 文件 |
|---|---|---|
| POST /cases | ✅ 已实现 | `routes/cases.py` |
| POST /cases/{id}/analyse | ✅ 已实现（mock 分析） | `routes/cases.py` |
| POST /cases/{id}/risks/{rid}/review | ✅ 已实现 | `routes/cases.py` |
| 其余 workflow-engine 端点 | ⬜ 待实现 | — |
| 全部 knowledge-orchestrator 端点 | ⬜ 待实现 | — |
| 全部 fhir-adapter 端点 | ⬜ 待实现 | — |
