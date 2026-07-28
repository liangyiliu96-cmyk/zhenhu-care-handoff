# 臻护 API 速查手册

> 臻护 v2.0 | 2026-07-21 | OpenAPI 164 路径 / 166 操作（含 `/v1/*` 兼容别名）· 3 认证模式 · 基于当前运行态

> **当前基线**：后端 `http://127.0.0.1:8001`，前端 `http://127.0.0.1:5173`，前端代理固定为 `5173 -> 8001`。FHIR Adapter `http://127.0.0.1:8300`。容器内部后端端口为 `8000`，不作为浏览器或本机脚本访问地址。接口总数、运行模式和生产边界见 [臻护-代码现状基线.md](臻护-代码现状基线.md)。本文按推荐业务入口组织，不将 `/v1/*` 兼容路径重复列为独立能力。

---

## 目录

1. [通用规范](#一通用规范)
2. [认证与系统](#二认证与系统) (7 端点)
3. [患者与入院](#三患者与入院) (7 端点)
4. [临床核心](#四临床核心) (11 端点)
5. [Dashboard 与数据查看](#五dashboard-与数据查看) (14 端点)
6. [照护管理](#六照护管理) (11 端点)
7. [出院流程](#七出院流程) (4 端点)
8. [病区视图](#八病区视图) (14 端点)
9. [护士端](#九护士端) (8 端点)
10. [AI 助手](#十ai-助手) (8 端点)
11. [管理端与运维](#十一管理端与运维)（含演示病例重置）
12. [RAG 知识库](#十二rag-知识库) (7 端点)
13. [CDS Hooks](#十三cds-hooks) (6 端点)
14. [FHIR 适配器](#十四fhir-适配器) (11 端点)
15. [错误码速查](#十五错误码速查)
16. [curl 快速测试](#十六curl-快速测试)

---

## 一、通用规范

### 1.1 Base URL

| 环境 | 地址 |
|------|------|
| 当前本地恢复联调 | `http://127.0.0.1:8001` (直接调用) / `http://127.0.0.1:5173` (通过 Vite Proxy) |
| 容器内部监听 | `8000`（仅供 Docker/Nginx 内部转发，不作为本机联调地址） |
| 生产部署 | `https://<domain>` (Nginx 反向代理) |

### 1.2 认证方式

| 模式 | Header | 说明 |
|------|------|------|
| **header** (dev) | `x-role: doctor` `x-title: 科主任` `x-department: 心内科` | 中文需 URL 编码: `%E7%A7%91%E4%B8%BB%E4%BB%BB` |
| **jwt** (staging) | `Authorization: Bearer <token>` | 先 `POST /login` 获取 token |
| **oidc** (prod) | `Authorization: Bearer <token>` | SSO 回调后自动注入 |

### 1.3 响应格式

**成功:**
```json
{
  "request_id": "uuid",
  "data": { ... }
}
```

**失败:**
```json
{
  "request_id": "uuid",
  "error": {
    "code": "STATE_VERSION_CONFLICT",
    "message": "状态版本冲突，请刷新后重试"
  }
}
```

### 1.4 并发控制

| 机制 | Header/参数 | 说明 |
|------|------|------|
| 乐观锁 | `expected_version` (body) | 写操作携带, 冲突返回 409 |
| 幂等性 | `Idempotency-Key` (header) | POST 防重复提交 |

### 1.5 端点汇总

| 方法 | 数量 | 域 |
|------|:--:|------|
| GET | 82 | 查询与读取 |
| POST | 73 | 创建与执行 |
| PATCH | 10 | 部分更新与状态变更 |

以上为当前 OpenAPI 操作数，包含 `/v1/*` 兼容别名；业务页面不应同时调用主路径与别名。

---

## 二、认证与系统

### `GET /health`

服务健康检查。

```
请求: 无认证
响应: { "status": "ok", "service": "inpatient-ward", "version": "0.3.0", "timestamp": "..." }
```

```bash
curl http://127.0.0.1:8001/health
```

---

### `GET /ready`

就绪探测 (含数据库连接检查)。

```
请求: 无认证
响应: { "status": "ready", "database": "connected" }
```

---

### `GET /inpatient/whoami`

当前认证身份查询。

```
请求: 任意认证模式
响应: {
  "actor_id": "dev-doc-shen",
  "name": "沈仲卫",
  "role": "doctor",
  "title": "科主任",
  "department": "心内科",
  "auth_mode": "header"
}
```

```bash
curl http://127.0.0.1:8001/inpatient/whoami \
  -H "x-role: doctor" -H "x-title: %E7%A7%91%E4%B8%BB%E4%BB%BB" -H "x-department: %E5%BF%83%E5%86%85%E7%A7%91"
```

---

### `POST /inpatient/login`

工号密码登录 (jwt 模式)。

```
请求: x-role: doctor
Body: { "job_number": "D001", "password": "pass123" }

响应: {
  "name": "沈仲卫",
  "role": "doctor",
  "title": "科主任",
  "department": "心内科",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "job_number": "D001"
}
```

---

### `GET /inpatient/admin-capabilities`

管理操作能力检查 (哪些运维操作在当前环境可用)。

```
请求: x-role: doctor (管理角色)
响应: {
  "is_manager": true,
  "environment": "development",
  "auth_mode": "header",
  "writes_enabled": true,
  "production_switch_enabled": true,
  "authorization_reason": "authorized",
  "required_permission": null,
  "operations": {
    "rag_reindex": true,
    "organization_seed": true,
    "seed_all": true,
    "clear_expired": true
  }
}
```

---

### `GET /inpatient/org`

组织架构 (人员与科室)。

```
请求: x-role: doctor (管理角色)
响应: {
  "staff": [
    { "name": "沈仲卫", "role": "doctor", "title": "科主任", "department": "心内科", "actor_id": "dev-doc-shen" }
  ],
  "departments": ["心内科", "呼吸科", "神内科", "消化科", "肾内科", "内分泌科", "骨科", "ICU"]
}
```

---

### `POST /inpatient/org/seed`

导入组织人员 (从 constants.py 同步)。

```
请求: x-role: doctor (管理角色)
响应: { "status": "ok", "staff_count": 54, "departments": 8 }
```

---

## 三、患者与入院

### `POST /inpatient/admissions`

创建入院记录, 触发 Agent 入院评估管线 (DDx + 评分 + 用药核对)。

```
请求: x-role: doctor
Body: {
  "name": "张建国",
  "mrn": "MRN-2026-07001",
  "gender": "male",
  "dob": "1954-03-15",
  "department": "心内科",
  "attending_doctor": "陆明泽",
  "chief_complaint": "胸闷气促 3 天,加重 1 天",
  "expected_version": 0
}

响应: {
  "patient_id": "patient-xxx",
  "admission_id": "adm-xxx",
  "workflow_state": "ddx_pending",
  "news2_score": 4,
  "ddx_preview": ["急性心力衰竭", "急性冠脉综合征", "肺栓塞"],
  "expected_version": 1
}
```

```bash
curl -X POST http://127.0.0.1:8001/inpatient/admissions \
  -H "Content-Type: application/json" \
  -H "x-role: doctor" -H "x-title: %E4%B8%BB%E6%B2%BB%E5%8C%BB%E5%B8%88" \
  -d '{...}'
```

---

### `GET /inpatient/admissions/{patient_id}`

查看入院详情。

```
响应: {
  "patient_id": "patient-xxx",
  "name": "张建国",
  "mrn": "MRN-2026-07001",
  "department": "心内科",
  "admission_date": "2026-07-20T14:05:00",
  "chief_complaint": "...",
  "workflow_state": "monitoring",
  "disease_template": { "name": "心力衰竭", ... }
}
```

---

### `POST /inpatient/admissions/{patient_id}/history`

录入病史 (触发病史生成 Agent)。

```
Body: {
  "chronic_diseases": ["高血压", "糖尿病"],
  "medications": ["赖诺普利 10mg qd", "二甲双胍 500mg bid"],
  "allergies": ["青霉素"],
  "surgical_history": ["胆囊切除术 2018"],
  "family_history": "父亲心梗 65 岁"
}

响应: {
  "hpi": "患者 72 岁男性, 因胸闷气促 3 天入院...",
  "ros": "心血管系统: 心悸, 呼吸困难...",
  "sufficient": true
}
```

---

### `POST /inpatient/admissions/{patient_id}/physical-exam`

录入体格检查。

```
Body: {
  "vital_signs": { "bp": "142/88", "hr": 96, "spo2": 93, "temp": 36.8, "rr": 22 },
  "general": "神志清楚, 半卧位, 口唇轻度发绀",
  "cardiovascular": "心率 96bpm, 律不齐, 各瓣膜区未闻及病理性杂音",
  "respiratory": "双肺底可闻及湿啰音",
  "other_systems": {}
}

响应: {
  "pe_narrative": "T 36.8℃, P 96bpm, R 22bpm, BP 142/88mmHg...",
  "abnormal_findings": ["双肺底湿啰音", "口唇发绀"]
}
```

---

### `POST /inpatient/admissions/{patient_id}/nursing`

护理综合录入 (护士看板快捷入口)。

```
请求: x-role: nurse
Body: {
  "vital_signs": { "spo2": 93, "hr": 96, "bp": "142/88" },
  "intake_ml": 800,
  "output_ml": 1600,
  "nursing_actions": "心电监护,q1h 出入量记录,吸氧 3L/min",
  "alerts": ["SPO2<94%"],
  "expected_version": 2
}

响应: { "status": "recorded", "version": 3, "alerts_triggered": 1 }
```

---

### `GET /patients`

护理患者目录 (护士端查看所有授权患者)。

```
请求: x-role: nurse
响应: {
  "patients": [
    { "patient_id": "patient-xxx", "name": "张建国", "bed": "15", "department": "心内科", "status": "active" }
  ],
  "total": 38
}
```

---

## 四、临床核心

### `POST /inpatient/review/{patient_id}`

医生提交审核 (DDx 确认/用药核对/出院签字)。

```
请求: x-role: doctor
Body: {
  "review_type": "ddx_confirm",
  "decision": "confirmed",
  "edits": [
    { "diagnosis": "急性心力衰竭", "action": "accept", "rank": 1 },
    { "diagnosis": "急性冠脉综合征", "action": "reject", "reason": "ECG 无 ST 段改变, hs-cTnI 正常" }
  ],
  "comment": "患者心衰表现典型, ACS 证据不足",
  "expected_version": 1
}

响应: {
  "status": "ok",
  "review_id": "rev-xxx",
  "workflow_state": "ddx_confirmed",
  "next_step": "doctor_med_confirm",
  "version": 2
}
```

**review_type 枚举:**
| 值 | 说明 |
|------|------|
| `ddx_confirm` | 鉴别诊断审核 |
| `medication_review` | 用药核对 |
| `discharge_sign` | 出院签字 |

**decision 枚举:**
| 值 | 说明 |
|------|------|
| `confirmed` | 确认通过 |
| `rejected` | 退回重审 |
| `signed` | 签字 (出院专用) |

---

### `POST /inpatient/{patient_id}/command`

医生临床指令。

```
Body: {
  "action": "transfer",
  "target": "肾内科",
  "reason": "eGFR 持续下降, 需肾内科联合管理",
  "expected_version": 5
}

响应: {
  "status": "ok",
  "command": "transfer_initiated",
  "transfer_reason": "CKD3 期进展, 建议肾内科会诊",
  "next_step": "pending_transfer"
}
```

**action 枚举:**
| 值 | 说明 | 响应变化 |
|------|------|------|
| `transfer` | 转科 | 返回 transfer_reason |
| `consult` | 发起会诊 | 返回 mdt_trigger |
| `discharge` | 发起出院 | 跳转出院流程 |
| `hold` | 暂停流程 | workflow_state → on_hold |
| `resume` | 恢复流程 | workflow_state → monitoring |

---

### `POST /inpatient/{patient_id}/query`

LLM 临床自由问询。

```
Body: { "question": "患者 GFR 持续下降, 是否考虑调整达比加群剂量?" }

响应: {
  "answer": "根据 2023 ESC 指南, 达比加群在 CrCl 15-29 mL/min 时推荐剂量为 75mg bid (国内 110mg bid)...",
  "citations": [
    { "source": "ESC 2023 AF Guideline", "section": "Anticoagulation in CKD" }
  ],
  "confidence": "high"
}
```

---

### `POST /inpatient/discharge/{patient_id}`

发起出院流程。

```
Body: { "reason": "病情稳定, 符合出院标准", "expected_version": 10 }

响应: {
  "status": "discharge_initiated",
  "discharge_criteria": { "met": 5, "total": 5, "details": [...] },
  "handoff_items": ["带药清单", "随访计划", "患教材料"],
  "patient_summary": { "total_days": 5, "primary_dx": "心力衰竭", ... }
}
```

---

### `POST /inpatient/discharge/{patient_id}/acknowledge-handoff`

出院交接确认 (交接闭环最后一步)。

```
Body: { "acknowledged_by": "护士", "note": "交接完成", "expected_version": 12 }

响应: { "status": "acknowledged", "handoff_completed_at": "..." }
```

---

### 报告/查询

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/inpatient/{id}/alerts` | 患者告警列表 |
| POST | `/inpatient/{id}/alerts/{alert_id}/acknowledge` | 确认告警 |
| POST | `/inpatient/{id}/alerts/{alert_id}/resolve` | 解决告警 |
| POST | `/inpatient/monitoring/{id}/vitals` | 录入生命体征 |
| POST | `/inpatient/monitoring/{id}/labs` | 录入检验结果 |

---

## 五、Dashboard 与数据查看

### `GET /inpatient/{patient_id}/dashboard`

完整患者 Dashboard (聚合视图)。

```
响应: {
  "patient_id": "patient-xxx",
  "name": "张建国",
  "disease_template": { "name": "心力衰竭", "department": "心内科" },
  "admission_info": { "date": "2026-07-20", "day": 3, "bed": "15" },
  "news2": { "score": 2, "trend": "improving", "components": {...} },
  "qsofa": { "score": 0, "status": "normal" },
  "padua": { "score": 5, "risk": "high", "recommendation": "LMWH 预防" },
  "morse": { "score": 45, "risk": "high" },
  "braden": { "score": 16, "risk": "moderate" },
  "vital_trends": {
    "spo2": [{ "timestamp": "...", "value": 93 }, ...],
    "hr": [{ "timestamp": "...", "value": 96 }, ...]
  },
  "lab_trends": {
    "creatinine": [{ "timestamp": "...", "value": 186, "unit": "μmol/L", "flag": "high" }],
    "bnp": [{ "timestamp": "...", "value": 2450, "unit": "pg/mL", "flag": "critical" }]
  },
  "soap_summary": {
    "subjective": "患者诉胸闷气促较昨日好转",
    "objective": "HR 88bpm, BP 138/84, SPO2 95%...",
    "assessment": "心功能改善, 容量负荷减轻",
    "plan": "继续呋塞米 20mg bid, 明日评估出院"
  },
  "medication_safety": {
    "interactions": [
      { "drug_a": "达比加群", "drug_b": "呋塞米", "severity": "moderate", "mechanism": "...", "recommendation": "..." }
    ],
    "allergy_contraindications": [],
    "gaps": [],
    "duplications": [],
    "warnings": []
  },
  "care_management": { "medications": [...], "investigations": [...], "mdt": [...], "education": [...], "followups": [...] },
  "version": 8
}
```

---

### 独立数据端点

| 方法 | 端点 | 说明 | 返回 |
|------|------|------|------|
| GET | `/inpatient/{id}/scores` | 评分详情 | NEWS2/qSOFA/Padua/Morse/Braden 分量 |
| GET | `/inpatient/{id}/vital-trends` | 体征趋势 | 时序数组 (HR/SpO2/BP/Temp) |
| GET | `/inpatient/{id}/lab-trends` | 检验趋势 | 时序数组 + 参考范围 + 异常标记 |
| GET | `/inpatient/{id}/rounds` | 查房记录 | SOAP 历史列表 |
| POST | `/inpatient/{id}/rounds/generate` | 生成本轮 AI 查房摘要 | 返回待医生核对的摘要/草稿 |
| PATCH | `/inpatient/{id}/rounds/{round_number}/edit` | 医生编辑查房内容 | 保留人工补充与版本控制 |
| POST | `/inpatient/{id}/rounds/{round_number}/review` | 医生核对查房 | 使草稿进入已核对状态 |
| GET | `/inpatient/{id}/nursing` | 护理记录 | 护理操作 + 出入量 + 评估记录 |
| GET | `/inpatient/{id}/clinical-note` | 临床笔记 | 笔记历史 |
| GET | `/inpatient/{id}/timeline` | 事件时间线 | 入院/评分/用药/查房 时序 |
| GET | `/inpatient/{id}/evidence` | 证据链 | RAG 引用 + Layer 来源 |
| GET | `/inpatient/{id}/clinical-brief` | 临床简报 | 关键信息摘要 |
| GET | `/inpatient/{id}/evidence-graph` | 证据图谱 | Neo4j 节点+关系 |
| GET | `/inpatient/{id}/follow-up-contacts` | 随访联系人 | 加密联系人列表 |
| GET | `/inpatient/{id}/agent-flow` | Agent 流程 | DAG 当前节点 + 路径 |
| GET | `/inpatient/{id}/discharge-summary` | 出院小结 | `?narrative=true` 触发 AI 叙事生成 |

---

## 六、照护管理

基础路径: `/inpatient/{patient_id}/care`

### `GET /inpatient/{patient_id}/care-management`

```
响应: {
  "medication_orders": [
    { "id": "med-1", "drug": "达比加群", "dose": "110mg bid", "status": "active", "started_at": "..." }
  ],
  "investigation_orders": [...],
  "mdt_requests": [...],
  "education_records": [...],
  "follow_up_tasks": [...],
  "version": 3
}
```

### CRUD 端点

| 方法 | 端点 | Body 关键字段 |
|------|------|------|
| POST | `/inpatient/{id}/care/medication-orders` | drug, dose, frequency, route, reason, expected_version |
| PATCH | `/inpatient/{id}/care/medication-orders/{order_id}` | status (active/suspended/completed/discontinued), expected_version |
| POST | `/inpatient/{id}/care/investigation-orders` | test_name, urgency, reason, expected_version |
| PATCH | `/inpatient/{id}/care/investigation-orders/{order_id}` | status, expected_version |
| POST | `/inpatient/{id}/care/mdt-requests` | specialties, reason, urgency, expected_version |
| PATCH | `/inpatient/{id}/care/mdt-requests/{request_id}` | decision (approved/rejected), summary, expected_version |
| POST | `/inpatient/{id}/care/education-records` | topic, recipient (patient/family/caregiver), teach_back, expected_version |
| POST | `/inpatient/{id}/care/follow-up-tasks` | type (phone/visit/message), scheduled_date, content, expected_version |
| PATCH | `/inpatient/{id}/care/follow-up-tasks/{task_id}` | status (completed/cancelled), audit_note, expected_version |

**PATCH 状态机:**
```
medication:  draft → active → suspended → completed / discontinued
MDT:         requested → approved / rejected
follow-up:   pending → completed / cancelled
```

---

## 七、出院流程

### 完整出院流 (Chain)

```
POST /inpatient/{id}/command   {action:"discharge"}  →  发起出院
  │
GET  /inpatient/{id}/discharge-summary                 →  审核小结
  │
POST /inpatient/review/{id}    {review_type:"discharge_sign"} → 签字
  │
POST /inpatient/discharge/{id}/acknowledge-handoff     →  交接确认
```

### `GET /inpatient/{patient_id}/discharge-summary`

```
查询: ?narrative=true  (可选, 触发 LLM 生成叙事段落)

响应: {
  "primary_diagnosis": "急性心力衰竭",
  "secondary_diagnoses": ["高血压 3 级", "2 型糖尿病", "CKD 3 期"],
  "hospital_course": "入院后予利尿、强心、扩血管治疗...",
  "discharge_medications": [
    { "drug": "达比加群", "dose": "110mg bid", "instruction": "餐后服用, 不可嚼碎" }
  ],
  "follow_up_plan": "7 天后社区随访, 30 天后心内科门诊",
  "key_events": [...],
  "handoff_items": [...],
  "narrative": "患者张建国, 男性, 72 岁, 因胸闷气促 3 天..."  // 仅 ?narrative=true
}
```

### `POST /inpatient/{patient_id}/discharge-summary/export-audit`

导出审计报告。

```
Body: { "format": "pdf", "include_audit_log": true }
响应: { "download_url": "/exports/discharge-xxx.pdf", "audit_entries": 12 }
```

---

## 八、病区视图

### 概览

| 方法 | 端点 | 说明 | 缓存 |
|------|------|------|:--:|
| GET | `/ward/overview` | 病区总览 (在院/入院/出院/告警) | — |
| GET | `/ward/patients` | 患者列表 (支持 `?department=` 筛选) | — |
| GET | `/ward/pending` | 待审核队列 (DDx/用药/出院) | — |
| GET | `/ward/priority` | AI 优先级排序 | — |
| GET | `/ward/workspace/alerts` | 工作台告警 | — |

### 数据看板

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/ward/alerts` | 病区告警汇总 | `?severity=critical/warning/info` |
| GET | `/ward/vitals` | 病区体征汇总 | `?vital=spo2/hr/bp/temp` |
| GET | `/ward/trends` | 病区趋势图 | `?metric=news2/news2_avg&days=7` |
| GET | `/ward/lab-summary` | 检验异常汇总 | `?department=心内科` |
| GET | `/ward/workload` | 工作量统计 | — |
| GET | `/ward/ai-summary` | AI 病区摘要 | — |
| GET | `/ward/shift-report` | 交接班报告 | — |
| GET | `/ward/insights` | 管理洞察 | — |
| GET | `/ward/visit-order` | 查房排序 | `?by=priority/news2` |

### 典型响应

**GET /ward/pending:**
```json
{
  "department": "心内科",
  "pending": [
    { "patient_id": "p-1", "name": "张建国", "bed": "15", "disease": "心力衰竭", "review_type": "ddx_confirm", "review_id": "rev-1", "state_version": 2 },
    { "patient_id": "p-2", "name": "陈国强", "bed": "22", "disease": "冠心病", "review_type": "discharge_sign", "review_id": "rev-3", "state_version": 5 }
  ],
  "count": 2,
  "summary": { "total_patients": 2, "total_items": 3, "ddx_pending": 1, "med_pending": 0, "discharge_pending": 1 }
}
```

**GET /ward/shift-report:**
```json
{
  "department": "心内科",
  "high_focus": [{ "patient_id": "p-1", "name": "张建国", "news2": 4, "alerts": 2, "reason": "心衰加重" }],
  "stable": [...],
  "discharge_today": [...],
  "ai_report": "本班重点关注: ① 张建国 NEWS2=4, 需密切监测出入量和 SPO2..."
}
```

---

## 九、护士端 (8 端点)

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/nurse/tasks` | 任务队列 (支持 `?department=` 筛选) |
| POST | `/nurse/tasks/{patient_id}/complete` | 完成任务 (含 idempotency 保护，state_version) |
| GET | `/nurse/ai-priority` | AI 优先级 (`?enhance_ai=true` 可选 LLM 增强) |
| GET | `/nurse/department-checklist` | 科室核查清单 (`?department=心内科`) |
| GET | `/nurse/kpi` | 护理 KPI (24h 窗口，按类型/科室分组) |
| GET | `/nurse/checklist-execution` | 制度执行状态（规则列表 + 关联患者 + 逾期统计） |
| POST | `/nurse/checklist-rules/{rule_id}/confirm` | 确认制度执行留痕（Body: `{ note: "..." }`） |
| GET | `/monitoring/overdue` | 逾期监测队列（护理端使用） |

### 典型请求

**GET /nurse/tasks:**
```json
{
  "tasks": [
    { "task_id": "t-1", "patient_id": "p-1", "patient_name": "张建国", "task_type": "vital_signs", "description": "生命体征监测", "status": "pending", "priority": 0.95, "due_by": "2026-07-20T20:00:00" }
  ],
  "total": 12,
  "pending": 8
}
```

**POST /nurse/tasks/{patient_id}/complete:**
```
Body: { "task_type": "vital_signs", "task_key": "t-1", "note": "SPO2 93%, HR 88", "expected_version": 2 }
Headers: Idempotency-Key: task-t-1-2026-07-20T20:00

响应: { "status": "completed", "kpi": { "completion_rate": 0.75, "streak": 3 } }
```

**task_type 枚举:** `vital_signs` / `nursing_actions` / `medication_review` / `protocol_check`

**GET /nurse/kpi:**
```json
{
  "open_tasks": 8,
  "completed_tasks": 24,
  "overdue_tasks": 2,
  "completion_rate": 0.75,
  "by_type": {
    "vital_signs": { "completed": 10, "pending": 3 },
    "nursing_actions": { "completed": 8, "pending": 2 }
  },
  "recent_completions": [...]
}
```

---

## 十、AI 助手

### 对话

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/assistant/chat` | 对话 (JSON 响应, 非流式) |
| POST | `/assistant/chat/stream` | 对话 (SSE 流式, 逐 token 推送) |
| POST | `/assistant/public/chat/stream` | 公共对话 (患者端, 不接入病历) |
| GET | `/assistant/quick-questions` | 快捷问题列表 |
| GET | `/assistant/public/quick-questions` | 公共快捷问题 |

### 会话管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/assistant/sessions` | 会话列表 |
| GET | `/assistant/session/{session_id}` | 会话详情 (含历史) |
| POST | `/assistant/session/{session_id}/reset` | 重置会话 (清空历史) |

### 流式对话详解

**POST /assistant/chat/stream:**
```
Body: { "message": "心衰患者的出入量管理要点是什么?", "assistantMode": "nurse", "patientId": "patient-xxx" }

响应 (SSE 格式):
data: {"type":"token","token":"心"}
data: {"type":"token","token":"衰"}
...
data: {"type":"token","token":"。"}
data: {"type":"complete","sessionId":"sess-xxx","sources":[{"topic":"心衰出入量管理","layer":"L8"}],"citations":[...]}
```

**assistantMode 枚举:**
| 值 | 助手名称 | 允许角色 |
|------|------|------|
| `doctor` | 查房助手 | doctor |
| `nurse` | 护理助手 | nurse |
| `pharmacist` | 用药助手 | doctor/pharmacist |
| `patient` | 健康小助手 | 公开 |
| `integrative` | 中西医协同 | doctor/integrative |

### 助手操作草稿

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/inpatient/{id}/assistant-action-drafts` | 草稿列表 |
| POST | `/inpatient/{id}/assistant-action-drafts/generate` | AI 生成草稿 |
| POST | `/inpatient/{id}/assistant-action-drafts` | 手动创建 |
| PATCH | `/inpatient/{id}/assistant-action-drafts/{draft_id}` | 更新草稿 |
| POST | `/inpatient/{id}/assistant-action-drafts/{draft_id}/approve` | 批准 (转为正式医嘱) |
| POST | `/inpatient/{id}/assistant-action-drafts/{draft_id}/reject` | 驳回 | 

**草稿状态:** `draft` → `approved` / `rejected`

---

## 十一、管理端与运维

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/inpatient/templates` | 病种模板列表 |
| GET | `/inpatient/db-stats` | 数据库统计 (表名+行数) |
| POST | `/inpatient/seed-all` | 导入全部基础数据 (人员+模板+清单) |
| POST | `/inpatient/clear-expired` | 清理过期热状态 |
| POST | `/inpatient/fixtures/reset-demo` | 受控重建心内科、呼吸科各 10 名演示患者；仅开发/演示环境 |
| GET | `/monitoring/overdue` | 体征逾期监测 |
| GET | `/admin/evidence-graph/status` | 证据图谱连接与数据状态 |
| GET | `/admin/evidence-graph/diseases/{disease_id}` | 病种证据规则与来源 |
| GET | `/admin/evidence-graph/diseases/{disease_id}/visualization` | 图谱可视化节点与关系 |
| POST | `/admin/evidence-graph/rebuild` | 重建 Neo4j 图谱（管理写操作） |

### POST /inpatient/seed-all
```bash
curl -X POST http://127.0.0.1:8001/inpatient/seed-all \
  -H "x-role: doctor" -H "x-title: %E7%A7%91%E4%B8%BB%E4%BB%BB"

# 响应:
{ "data": { "org": 54, "templates": 22, "checklist": 67, "status": "completed" } }
```

### POST /inpatient/fixtures/reset-demo

受控替换虚构演示患者。需要管理角色 capability `demo_patient_reset`；生产环境固定返回拒绝。前端使用时必须展示破坏性确认说明。

```bash
curl -X POST http://127.0.0.1:8001/inpatient/fixtures/reset-demo \
  -H "Content-Type: application/json" \
  -H "x-role: doctor" -H "x-title: 科主任" \
  -d '{"confirmed":true,"purge_runtime":true}'
```

`purge_runtime=true` 会清除开发/演示运行库中所有历史患者状态，并重建 `2026-07-21.1` 演示包（心内科、呼吸科各 10 例）。知识库、组织、模板和审计日志不在清理范围内。响应含 `pack_version`、`removed`、`total`、`by_department`、`patient_ids` 与 `audit_id`。

### GET /inpatient/db-stats
```json
{
  "tables": { "inpatient_patients": 45, "inpatient_records": 52, "audit_logs": 1230 },
  "storage": { "backend": "sqlite", "size_mb": 8.2 }
}
```

### GET /inpatient/templates
```json
{
  "templates": ["heart_failure", "hypertension", "cad", "copd", "diabetes", "stroke", "aki", "ckd", "cirrhosis", "atrial_fibrillation", "asthma", "pe", "pancreatitis", "pneumonia", "sepsis", "hip_fracture", "delirium", "gi_bleeding", "hyperthyroidism", "post_surgery", "severe_anemia", "tumor_chemo"],
  "total": 22
}
```

---

## 十二、RAG 知识库

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/admin/rag/dashboard` | 知识库健康仪表板 (16 层热力图、缓存状态) |
| GET | `/admin/rag/entries` | 条目搜索 (`?search=&layer=&page=&page_size=`，覆盖 topic/text/source/category/disease/department) |
| GET | `/admin/rag/preview` | 管理端语义检索预览 (`?query=&layers=&top_k=`) |
| GET | `/admin/rag/diagnostics` | 失败层、缺失与可维护性诊断 |
| POST | `/admin/rag/reindex` | 重建全库索引 (清空→重建) |
| GET | `/admin/rag/maintenance-log` | 维护日志 |
| GET | `/inpatient/rag/search` | 兼容/直接诊断的向量检索 |
| GET | `/inpatient/rag/browse` | 兼容/直接诊断的知识浏览 |
| GET | `/inpatient/rag/validate` | 兼容/直接诊断的完整性检查 |

### GET /inpatient/rag/search
```
请求: ?query=心衰出入量管理&layer=L8&top_k=5

响应: {
  "results": [
    { "score": 0.52, "topic": "心衰出入量管理", "text": "每日晨起排尿后测体重...", "layer": "L8", "category": "心内科护理" },
    { "score": 0.48, "topic": "心力衰竭患者自我管理", "text": "限水 1.5-2L/日...", "layer": "L9", "category": "心内科自护" }
  ],
  "query": "心衰出入量管理",
  "elapsed_ms": 2105
}
```

### POST /admin/rag/reindex
```
响应: { "data": { "layers": {"L1":6,"L2":18,"L3":22,"L4":67,"L5":25,...}, "total": 385 } }
耗时: 30-60s (385 条 × 384 维 MiniLM CPU 编码)
```

### GET /admin/rag/dashboard
```json
{
  "total_documents": 385,
  "total_layers": 16,
  "last_indexed": "2026-07-21T00:30:00",
  "needs_attention": false,
  "issues": [],
  "layers": {
    "L1": { "collection": "clinical_scoring", "expected": 6, "actual": 6, "health": "ok", "category": "评分规则" }
  }
}
```

### 管理端推荐检索链

管理页面应先用 `GET /admin/rag/entries` 做可解释的关键词检索，再用 `GET /admin/rag/preview` 做语义召回预览。`preview` 首次调用可能加载嵌入模型；前端已用较长 Agent 超时并利用 Redis/运行时缓存，运维时不要把冷启动误判为索引丢失。

---

## 十三、CDS Hooks

一期展示不交互 (HL7 FHIR CDS Hooks 规范)。

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/cds-services` | 服务发现 |
| GET | `/cds-services/status` | 集成状态 |
| POST | `/cds-services/zhenhu-admission-confirm` | 入院确认 Hook |
| POST | `/cds-services/zhenhu-medication-confirm` | 用药确认 Hook |
| POST | `/cds-services/zhenhu-discharge-sign` | 出院签字 Hook |
| POST | `/cds-services/zhenhu-clinical-summary` | 临床摘要 Hook |

**典型请求 (CDS Hooks 标准):**
```json
{
  "hook": "patient-view",
  "hookInstance": "uuid",
  "context": {
    "patientId": "patient-xxx",
    "encounterId": "enc-xxx",
    "userId": "doctor-Lu"
  }
}
```

---

## 十四、FHIR 适配器 (11 端点)

FHIR Adapter 独立服务，端口 `http://127.0.0.1:8300`，将临床数据转换为 FHIR R4 标准格式。住院端通过 BackgroundTasks + fhir_sync 同步数据。

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/fhir/Patient/{patient_id}` | 查询脱敏患者信息 |
| GET | `/fhir/Patient/{patient_id}/CarePlan` | 患者照护计划（出院+慢病） |
| POST | `/fhir/Consent` | 创建知情同意记录 |
| GET | `/fhir/AuditEvent?patient=...&page=...&size=...` | 查询审计事件（分页） |
| POST | `/fhir/Observation` | 写入体征/检验（住院端自动同步） |
| POST | `/fhir/Condition` | 写入诊断/DDx（住院端自动同步） |
| POST | `/fhir/AuditEvent` | 写入审计事件（outbox 投递） |
| POST | `/fhir/MedicationRequest` | 写入用药申请 |
| GET | `/patient/{patient_id}/care-view` | 患者照护视图聚合（需 knowledge-orchestrator） |
| GET | `/patient/{patient_id}/summary` | 患者脱敏摘要 |
| GET | `/health` | 健康检查 |

**数据同步机制**：inpatient-ward → BackgroundTasks/fhir_sync → fhir-adapter POST 端点。体征/检验上报后自动触发 Observation 同步，审计事件通过 outbox 事务投递。`FHIR_ADAPTER_URL=http://127.0.0.1:8300/fhir`。

**脱敏规则**：Name → 首字+**，Identifier → TOKEN-后4位。每次读写自动写入 `fhir_audit_events` 表。

**8 张 FHIR 资源表**：patients / encounters / conditions / observations / medication_requests / care_plans / consents / fhir_audit_events。

---

## 十五、错误码速查

| HTTP | code | 含义 | 触发条件 |
|:--:|------|------|------|
| 400 | `VALIDATION_ERROR` | 请求参数校验失败 | Pydantic 验证不通过 |
| 401 | `UNAUTHORIZED` | 未认证 | 缺少认证 header / token 过期 |
| 403 | `FORBIDDEN` | 无权限 | 角色不匹配 (如 nurse 访问 doctor-only) |
| 404 | `NOT_FOUND` | 资源不存在 | patient_id 错误 |
| 409 | `STATE_VERSION_CONFLICT` | 版本冲突 | expected_version 不匹配 |
| 409 | `DUPLICATE_REQUEST` | 重复请求 | Idempotency-Key 已使用 |
| 429 | `RATE_LIMITED` | 请求限流 | 超过频率限制 |
| 500 | `INTERNAL_ERROR` | 内部错误 | 服务异常 |
| 503 | `MILVUS_UNAVAILABLE` | 向量库不可用 | Milvus 连接失败 (RAG 降级) |
| 503 | `LLM_UNAVAILABLE` | LLM 不可用 | DeepSeek API 连接失败 (回退规则) |

**409 处理指引:**
```
1. 前端保留用户填写的本地草稿 (不清空表单)
2. 弹出提示: "数据已被其他人修改, 请刷新页面后重新提交"
3. 用户点"刷新" → 重新 GET 最新数据 → 可手动合并草稿
4. 绝不自动重放写操作
```

---

## 十六、curl 快速测试

```bash
# ── 0. 环境变量 ──
BASE="http://127.0.0.1:8001"
AUTH='-H "x-role: doctor" -H "x-title: %E7%A7%91%E4%B8%BB%E4%BB%BB" -H "x-department: %E5%BF%83%E5%86%85%E7%A7%91"'

# ── 1. 健康 & 认证 ──
curl $BASE/health
curl $BASE/inpatient/whoami $AUTH

# ── 2. 入院 ──
curl -X POST $BASE/inpatient/admissions \
  -H "Content-Type: application/json" $AUTH \
  -d '{"name":"测试患者","mrn":"TEST-001","gender":"male","dob":"1954-03-15","department":"心内科","chief_complaint":"胸闷3天","expected_version":0}'

# ── 3. Dashboard ──
curl $BASE/inpatient/{patient_id}/dashboard $AUTH
curl $BASE/inpatient/{patient_id}/scores $AUTH
curl $BASE/inpatient/{patient_id}/vital-trends $AUTH
curl $BASE/inpatient/{patient_id}/lab-trends $AUTH
curl $BASE/inpatient/{patient_id}/evidence $AUTH

# ── 4. 病区 ──
curl $BASE/ward/overview $AUTH
curl $BASE/ward/pending $AUTH
curl $BASE/ward/patients $AUTH
curl $BASE/ward/alerts $AUTH
curl $BASE/ward/shift-report $AUTH

# ── 5. 护理 ──
curl $BASE/nurse/tasks -H "x-role: nurse" -H "x-title: %E4%B8%BB%E7%AE%A1%E6%8A%A4%E5%B8%88"
curl $BASE/nurse/department-checklist?department=心内科 -H "x-role: nurse"
curl $BASE/nurse/kpi -H "x-role: nurse"

# ── 6. 助手 ──
curl -X POST $BASE/assistant/chat \
  -H "Content-Type: application/json" $AUTH \
  -d '{"message":"心衰出入量管理要点?","assistantMode":"doctor","patientId":"patient-xxx"}'

# ── 7. 知识库 ──
curl $BASE/admin/rag/dashboard $AUTH
curl "$BASE/admin/rag/entries?search=心衰&layer=L5&page=1&page_size=10" $AUTH
curl "$BASE/admin/rag/preview?query=心衰出入量&layers=L8&top_k=3" $AUTH

# ── 8. 管理端 ──
curl $BASE/inpatient/org $AUTH
curl $BASE/inpatient/templates $AUTH
curl $BASE/inpatient/db-stats $AUTH
curl -X POST $BASE/inpatient/seed-all $AUTH
```

---

> 文档版本 v2.0 · OpenAPI 164 路径 / 166 操作（含兼容别名）· 2026-07-21 · 基于当前运行态与源码
