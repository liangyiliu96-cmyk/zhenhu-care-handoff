# 09-Cardio改造成果说明

> **改造日期**: 2026-07-16 | **版本**: v0.4 | **测试**: 138 passed, 0 errors
>
> **阶段A**: 5个参考项目新模式融入(HITL重评/事件文档链/KG追问/自动MDT/PlanDefinition)
> **阶段B**: 11个工程差距修复(表名复数/双ID/updated_at/routes/lifespan/async tests/模板迁移)

## 改造总览

| 阶段 | 内容 | 测试 |
|---|---|---|
| 1-7 (原方案) | legacy归档, namespace, 去硬编码, Agent框架, Harness, 桥接, 打磨 | 114 ✅ |
| **A** | **5个参考项目新模式**: HITL自适应重评 + 事件驱动文档链 + KG结构化追问 + 风险驱动MDT + PlanDefinition/$apply | +6 新测试 |
| **B** | **11个工程差距修复**: 表名复数, 双ID, updated_at, routes, lifespan, async tests, 模板迁移 | +24 测试 |
| **合计** | **全面适配臻护主项目** | **138 ✅** |

## 架构全景(实际目录)

```
cardio-inpatient-collab/
├── legacy/                          # 阶段1: 原前后端归档
├── backend/
│   ├── app/src/zhenhu/inpatient/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI + 臻护中间件
│   │   ├── middleware.py            # RequestIdMiddleware + error handlers
│   │   ├── models.py                # 12表(snake_case对齐臻护)
│   │   ├── schemas.py               # Pydantic v2 + UnifiedResponse
│   │   ├── agent/
│   │   │   ├── graph.py             # StateGraph 7节点编排
│   │   │   ├── nodes.py             # admission→triage→…→patient_confirm
│   │   │   ├── tools.py             # search_knowledge / check_discharge_criteria
│   │   │   ├── harness.py           # Pydantic校验 + source_none检测 + 模板回退
│   │   │   └── interrupt.py         # HumanInterrupt封装
│   │   ├── domain/
│   │   └── hooks/
│   │       └── zhenhu_bridge.py     # 3桥接: discharge→cases / search→knowledge / patient→fhir
│   ├── disease_templates/
│   │   ├── hypertension.json
│   │   ├── heart_failure.json
│   │   └── diabetes.json
│   └── tests/                       # 21文件 | 114 passed
│       ├── test_agent_harness.py
│       ├── test_agent_nodes.py
│       ├── conftest.py
│       ├── unit/ (15 tests) + integration/
```

## Agent设计

**7节点** StateGraph: `admission → triage → monitoring → discharge → handoff → doctor_review → patient_confirm`

| 模式 | 来源 | 改动 |
|---|---|---|
| **HITL 自适应重评** | carehandoff | `doctor_review` 支持 accept/edit/dismiss，dismiss 触发 `pending_reevaluation` |
| **事件驱动文档链** | chronicdisease | `after_monitoring` 基于 `document_chain` 路由，非硬编码边 |
| **KG 结构化追问** | chronicdisease | 3 个病种模板各含 `followup_questions[]`(ehr-kg/ddx-kg 溯源) |
| **风险驱动自动 MDT** | chronicdisease | 高危自动标记 `mdt_required` + `mdt_roles` |
| **PlanDefinition/$apply** | medplum | 出院桥接先构造 PlanDefinition(action[]) 再调 workflow |

## 臻护对接点

| 桥接 | 方向 | 端点 |
|---|---|---|
| 出院→创建病例 | Cardio→臻护 | POST `{WORKFLOW_URL}/cases` |
| RAG检索 | Cardio→臻护 | GET `{KNOWLEDGE_URL}/knowledge/search` |
| 患者摘要 | Cardio→臻护 | GET `{FHIR_URL}/fhir/Patient/{id}` |

## 病种模板

`hypertension.json`(原硬编码值映射) + `heart_failure.json` + `diabetes.json`

统一格式: `disease_id → vital_signs[] → risk_factors[] → discharge_criteria[] → handoff_instructions[] → agent_config`

## 与臻护关系

Cardio住院协同(入院评估→持续监测→出院判断)→出院交接(handoff_items+医生审核+患者确认)→臻护出院后管理(workflow病例+RAG知识库+FHIR患者档案)

## 待办

- 阶段5: fixture→真实LLM替换
- PoC验证: poc/cardio/ 对拉三服务
- 迁移: →services/inpatient-ward/
