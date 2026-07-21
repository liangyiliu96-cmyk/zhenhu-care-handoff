# 臻护 · Agent 节点输入输出规范

> 臻护 v2.0 | classic 模式下的 27 个核心编排节点 × 4 条临床流程 | Agent 开发 / 测试 / 调优

> **当前校准**：本表描述当前 `GRAPH_MODE=classic` 的核心节点与人工审核边界。`GRAPH_MODE=stateful` 尚未完成持久化 interrupt/resume 验收，会被启动校验拒绝；不能把本表理解为已启用 stateful LangGraph。完整运行边界见 [臻护-代码现状基线.md](臻护-代码现状基线.md)。

---

## 目录

1. [入院流程](#一入院流程) (7 节点)
2. [评分与风险评估](#二评分与风险评估) (7 节点)
3. [住院监测流程](#三住院监测流程) (8 节点)
4. [出院流程](#四出院流程) (5 节点)
5. [LLM 使用总表](#五llm-使用总表)

---

## 一、入院流程

### 1.1 节点链

```
admission → history_taking → physical_exam → ddx
  → medication_reconciliation → triage → doctor_confirm
```

### 1.2 逐节点详表

| # | 节点 | 文件 | LLM | 输入字段 | 输出字段 | 前置 | 后置 | 触发条件 |
|:--:|------|------|:--:|------|------|:--:|:--:|------|
| 1 | node_admission | nodes_admission.py | ❌ | patient_id, fhir_data(可选) | disease_template, patient_data, admission_assessment | — | history_taking | POST /admissions |
| 2 | node_history_taking | nodes_clinical.py | ✅ | admission_assessment, patient_data | hpi, ros, history_content, insufficient_data | admission | physical_exam | 自动 |
| 3 | node_physical_exam | nodes_clinical.py | ✅ | history_content, patient_data | pe_narrative, abnormal_findings, insufficient_data | history_taking | ddx | 自动 |
| 4 | node_ddx | nodes_clinical.py | ✅+R | disease_template, pe_narrative, history_content, patient_data | ddx_list (diagnosis/probability/evidence), ddx_unavailable | physical_exam | medication_reconciliation | 自动 |
| 5 | node_medication_reconciliation | nodes_admission.py | ✅+R | ddx_list, current_medications, allergies | medication_safety (interactions/gaps/dups/warnings) | ddx | triage | 自动 |
| 6 | node_triage | nodes_admission.py | ✅* | ddx_list, medication_safety, disease_template, patient_data | risk_level (low/medium/high/critical), risk_summary | medication_reconciliation | doctor_confirm | 自动 |
| 7 | node_doctor_confirm | nodes_checkpoints.py | ❌ | ddx_list, medication_safety, risk_level | approval_status, pending_review (如果需人工确认) | triage | batch_scoring | Human-in-loop |

---

## 二、评分与风险评估

### 2.1 节点链

```
batch_scoring (并发调用):
  ├── node_news2
  ├── node_qsofa
  ├── node_padua_score
  └── node_vte_prophylaxis

node_stroke_antithrombotic (并行)
node_mdt_trigger (后续)
```

### 2.2 逐节点详表

| # | 节点 | 文件 | LLM | 输入字段 | 输出字段 | 触发条件 |
|:--:|------|------|:--:|------|------|------|
| 8 | node_batch_scoring | nodes_batch.py | ❌ | disease_template, patient_data, admission_assessment | scores{} (news2/qsofa/padua/vte 聚合) | 包装器, 内部并发 |
| 9 | node_news2 | nodes_scoring.py | ✅* | vital_signs (RR/SpO2/吸氧/SBP/HR/意识/体温) | news2_score (0-20), news2_components{}, news2_advice (≥5 触发 LLM) | 规则查表→≥5 分触发 LLM 建议 |
| 10 | node_qsofa | nodes_scoring.py | ✅* | vital_signs (RR/SBP/GCS) | qsofa_score (0-3), qsofa_advice (≥2 触发 LLM) | 规则阈值→≥2 分触发 LLM 建议 |
| 11 | node_padua_score | nodes_scoring.py | ❌ | patient_data (年龄/BMI/制动/肿瘤/既往VTE/等 11 项) | padua_score (0-20), padua_risk_level, padua_details{} | 纯规则关键词匹配打分 |
| 12 | node_vte_prophylaxis | nodes_scoring.py | ❌ | current_medications, allergies, contraindications, padua_score | vte_recommendation (LMWH/机械/无所/禁忌), vte_contraindication | 纯规则关键词匹配药物/禁忌 |
| 13 | node_stroke_antithrombotic | nodes_scoring.py | ❌ | disease_template (stroke?), current_medications, allergies | stroke_antithrombotic_plan | 纯规则关键词匹配卒中+抗栓药物 |
| 14 | node_mdt_trigger | nodes_scoring.py | ❌ | alerts[], disease_template | mdt_recommendation (是否触发会诊+建议科室) | 纯规则告警数 vs 阈值 |

---

## 三、住院监测流程

### 3.1 节点链

```
daily_round → nursing → shift_summary → lab_review
  → monitoring → medication_adjust → transfer → doctor_review
```

### 3.2 逐节点详表

| # | 节点 | 文件 | LLM | 输入字段 | 输出字段 | 触发条件 |
|:--:|------|------|:--:|------|------|------|
| 15 | node_daily_round | nodes_monitoring.py | ✅+R | vital_signs, lab_results, current_state, disease_template | soap_summary (S/O/A/P), round_plan | doctor_confirm 后自动/触发 |
| 16 | node_nursing | nodes_clinical.py | ✅* | dep_checklist, vital_signs, alerts, disease_template | nursing_plan, nursing_actions, nursing_checklist_status | 需 LLM 异常体征/有告警/无 checklist 科室 |
| 17 | node_shift_summary | nodes_clinical.py | ✅+R | nursing_plan, vital_trends, alerts, disease_template | shift_report (high_focus/stable/discharge_today 三组), ai_report (复杂病例) | 交班时触发, 规则基线→复杂病例 LLM |
| 18 | node_lab_review | nodes_monitoring.py | ✅ | lab_results[], reference_ranges | lab_interpretation, abnormal_findings[], critical_flags[] | 有新检验结果时触发 |
| 19 | node_monitoring | nodes_monitoring.py | ❌ | vital_trends, lab_trends, disease_template (discharge_criteria) | discharge_readiness (met/total), complication_watch[], monitoring_status | 纯规则: 出院标准检查 + 并发症监测正则 |
| 20 | node_medication_adjust | nodes_monitoring.py | ✅* | medication_safety, lab_trends (异常), monitoring_status | medication_adjustments[], adjustment_reason | 连续异常检测→≥2 次触发 LLM |
| 21 | node_transfer | nodes_monitoring.py | ✅* | monitoring_status, disease_template, department_rules | transfer_needed (bool), transfer_reason, target_department | 规则决策: 休克/RR/GCS→需转科时 LLM 理由 |
| 22 | node_doctor_review | nodes_handoff.py | ✅* | review_items[], doctor_feedback | review_decisions[], review_notes (仅驳回时触发 LLM) | 医生审核反馈→有驳回项时 LLM 生成备注 |

---

## 四、出院流程

### 4.1 节点链

```
discharge → handoff → doctor_discharge_sign → patient_confirm
```

### 4.2 逐节点详表

| # | 节点 | 文件 | LLM | 输入字段 | 输出字段 | 触发条件 |
|:--:|------|------|:--:|------|------|------|
| 23 | node_discharge | nodes_handoff.py | ❌ | patient_id, disease_template, handoff_items | discharge_decision, bridge_result, knowledge_context, patient_summary | POST `/inpatient/discharge/{id}` 发起正式出院链；不支持旧的直接执行出院 |
| 24 | node_handoff | nodes_handoff.py | ✅+R | disease_template, discharge_instruction, patient_summary | handoff_items[], personalized_notes (LLM 补充) | discharge bridge 成功后, 模板基线→LLM 个性化 |
| 25 | node_doctor_discharge_sign | nodes_checkpoints.py | ❌ | handoff_items[], doctor_id | signature_status, pending_sign (如果需签字) | 纯状态机 |
| 26 | node_doctor_med_confirm | nodes_checkpoints.py | ❌ | medication_reconciliation_result | med_confirm_status | 纯状态机 |
| 27 | node_patient_confirm | nodes_handoff.py | ❌ | handoff_acknowledged?, teach_back_complete?, bridge_complete?, signature_status | all_confirmed (bool), missing_confirmations[] | 纯规则: 4 项布尔检查 |

---

## 五、LLM 使用总表

| 分类 | 数量 | 节点 | LLM 调用时机 | 降级策略 |
|------|:--:|------|------|------|
| 纯 LLM | 3 | history_taking, physical_exam, lab_review | 每次执行 | insufficient_data→空结构体, 不阻断 |
| LLM + 规则回退 | 5 | ddx, daily_round, shift_summary, handoff, medication_reconciliation | 每次执行, LLM 增强规则基线 | 3 次 Pydantic 重试→规则结果 |
| 规则 + LLM 建议 | 5 | news2, qsofa, triage, transfer, doctor_review | 仅在高风险/特殊情况下调用 | 规则结果不变, 仅跳过建议文本 |
| 条件 LLM | 2 | nursing, medication_adjust | 仅在异常体征/连续异常时调用 | 规则结果保留, LLM 仅补充 |
| 纯规则 | 10 | admission, vte_prophylaxis, stroke_antithrombotic, mdt_trigger, padua_score, monitoring, discharge, patient_confirm, doctor_confirm, doctor_med_confirm, doctor_discharge_sign | 永不调用 | — |
| 编排包装 | 1 | batch_scoring | 内部并发 4 节点 | — |
| **总计** | **27** | **18 个节点涉及 LLM, 10 个纯规则** | | |

### 5.1 降级策略统一规则

```
所有 LLM 调用包裹在 try/except 中:
  ├─ safe_llm_invoke: 失败返回 None (节点继续)
  ├─ deep_invoke: 失败返回空结果 (不阻断流程)
  └─ 规则结果永不因 LLM 失败而丢失
```

### 5.2 状态传递

```
节点间通过 state dict 传递:
  state = {
    "patient_id": str,
    "disease_template": dict,
    "patient_data": dict,
    "phase": str,
    "document_chain": list[str],       // 已执行的节点列表
    "ddx_list": list[dict],
    "scores": dict,
    "medication_safety": dict,
    ...
  }

每次节点执行:
  current_state → node_func(current_state) → updated_state (merge)
```

### 5.3 前端可观测与人工确认

| 场景 | 前端入口 | 后端契约 | 安全边界 |
|------|------|------|------|
| 当前编排路径 | 患者工作区 Agent 流程面板 | `GET /inpatient/{id}/agent-flow` | 仅展示状态和节点，不授予自动执行权限 |
| AI 查房 | 查房专区 | `GET /rounds`、`POST /rounds/generate`、`PATCH /rounds/{n}/edit`、`POST /rounds/{n}/review` | 医生编辑和核对后才进入临床处置 |
| 建议转操作草稿 | 患者助手/草稿面板 | `/assistant-action-drafts` 读取、生成、审批、驳回 | 草稿不等于医嘱，必须人工批准 |
| 出院 | 出院流程页 | `POST /inpatient/discharge/{id}`、审核与交接接口 | 医生指令、卡点审核、签字/交接不可绕过 |

---

> 文档版本 v2.0 · classic 模式 27 个核心节点 · 2026-07-21 · 基于 `agent/graph.py`、`agent/nodes_*.py` 与前端调用链
