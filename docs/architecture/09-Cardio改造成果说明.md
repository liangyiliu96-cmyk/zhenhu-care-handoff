# 09-Cardio改造成果说明

> **改造日期**: 2026-07-16 | **测试**: 114 passed, 0 errors

## 改造总览

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | legacy归档+前端删除 | ✅ |
| 2 | zhenhu namespace+中间件+28→12表 | ✅ |
| 3 | 去心血管硬编码(bp→vital_sign)+3病种模板 | ✅ |
| 4 | LangGraph Agent 7节点框架 | ✅ |
| 5 | Harness安全护栏(校验/溯源/回退) | ✅ |
| 6 | 臻护桥接(出院/workflow+检索/knowledge+患者/fhir) | ✅ |
| 7 | 回归测试+QA问题修复+打磨 | ✅ |

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

7节点 StateGraph: `admission → triage → monitoring → discharge → handoff → doctor_review → patient_confirm`

- **interrupt**: 仅 `doctor_review` 触发 HumanInterrupt(checkpoint冻结),其余节点自动流转
- **Harness**: `validate_handoff_items()` Pydantic校验 → `check_source_type()` score阈值(source_none/source_knowledge) → `fallback_to_template()` 模板回退

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
