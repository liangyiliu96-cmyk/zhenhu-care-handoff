# FHIR 适配与医院集成 v0.2

**状态：** 正式工程架构基线
**依据：** 需求 §6.1 FHIR 映射目标；架构总览 §2 fhir-adapter 服务；数据模型 01 §2.3 fhir-adapter 表结构

---

## 1. fhir-adapter 服务边界

```
HIS/EMR/LIS（阶段 0 模拟 / 阶段 1 真实）
        ↓
fhir-adapter（FastAPI :8003）
  ├── 协议适配层：HL7 v2/v3 → FHIR R4 映射
  ├── 资源校验层：fhir.resources 校验 → Pydantic 输出
  ├── Patient Compartment：按患者隔离资源集合
  ├── 脱敏层：姓名→token、身份证→hash、地址→模糊化
  └── 审计层：每次访问写入 fhir_audit_events
        ↓
workflow-engine → 结构化 FHIR 快照 + 字段溯源
```

| 边界 | 说明 | 需求依据 |
|------|------|----------|
| 只读接入 | fhir-adapter 不写回医院生产系统 | 需求 §0 PoC 基线 |
| 脱敏输出 | 所有 PII 字段在输出前脱敏：`name_token`、`identifier_token`、`address_city` | 需求 §7 安全审计 |
| 输入快照 | `GET /fhir/Patient/{id}/snapshot` 返回完整的脱敏病例快照，`input_snapshot_id` 作只读引用 | 数据模型 01 §4 |
| 服务隔离 | 独立 MySQL `zhenhu_fhir`，不直连医院业务库 | 数据模型 01 §4 |

---

## 2. FHIR 资源映射（8 表）

| 业务数据 | FHIR 资源 | 数据库表 | 关键字段 |
|----------|----------|---------|----------|
| 患者基本信息 | `Patient` | `patients` | `name_token`, `gender`, `birth_date`, `address_city` |
| 就诊记录 | `Encounter` | `encounters` | `status`, `class`, `period_start/end`, `service_type` |
| 诊断 | `Condition` | `conditions` | `code`, `code_system`, `clinical_status`, `onset_date` |
| 检验/体征 | `Observation` | `observations` | `code`, `value_quantity`, `value_unit`, `effective_at` |
| 用药医嘱 | `MedicationRequest` | `medication_requests` | `medication_code`, `medication_name`, `dosage_text` |
| 照护计划 | `CarePlan` | `care_plans` | `title`, `status`, `category`, `period_start/end` |
| 知情同意 | `Consent` | `consents` | `scope`, `status`, `provision_json` |
| 访问审计 | `AuditEvent` | `fhir_audit_events` | `entity_type`, `entity_id`, `action(C/R/U/D)`, `actor` |

**参考 PoC：** PoC 的 mock 病例数据结构（`snapshot.patient` / `snapshot.encounter` / `snapshot.medications` / `snapshot.labs`）→ 正式化为上述 8 张表，字段增加溯源元数据（`code_system`、`recorded_at`）。

---

## 3. Patient Compartment

| 原则 | 实现 |
|------|------|
| 资源级隔离 | 所有 API `GET /fhir/{ResourceType}` 必须携带 `patient_id` 过滤 |
| 访问策略 | `Consent.provision_json` 记录授权范围，网关在转发前校验 |
| 字段级脱敏 | PII 字段输出 token，原始值不离开 fhir-adapter |

**参考需求 §6.1：** "访问策略应以本院数据模型、实际角色和最小必要原则为准，不能照搬参考框架的 compartment 或 account 语义。"

---

## 4. 待确认

| 事项 | 影响 | 决策者 |
|------|------|--------|
| **医院系统接口协议**：HL7 v2/v3 / FHIR R4 / 定制 API？ | fhir-adapter 协议适配层选型 | 医院信息科 |
| **CarePlan 双模式**：出院交接计划（short-term）vs 慢病照护计划（long-term）的实例化规则 | `care_plans` 表字段设计 | 需求 §6.1 |
| **患者索引**：是否使用医院 EMPI 主索引？ | `patients.patient_id` 取值来源 | 医院信息科 |

---

## 阶段对照

| 能力 | 阶段 0（当前） | 阶段 1 | 阶段 2 |
|---|---|---|---|
| 服务状态 | `services/fhir-adapter/` 未创建 | FastAPI 骨架 + 8 表 ORM | 完整 FHIR R4 服务端 |
| 医院对接 | PoC 用 mock `snapshot` 数据结构 | HL7 v2 / FHIR R4 适配层 | 医院 HIS/EMR/LIS 实时对接 |
| Patient Compartment | 无 | MySQL 行级过滤 | Keycloak 资源级权限联动 |
| CarePlan 双模式 | 无 | 出院计划 + 慢病计划 两条 CarePlan | PlanDefinition 模板驱动 |
