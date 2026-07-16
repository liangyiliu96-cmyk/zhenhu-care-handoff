# 08-Cardio改造方案

> **作者**: 高见远(臻护架构师)
> **日期**: 2026-07-16
> **状态**: 方案评审期
> **来源**: Cardio心血管住院协同演示系统 v0.1(28表,152测试,AI全fixture)

---

## 1. 改造目标

Cardio是高血压心血管住院协同 MVP,四端角色(医生/家属/执行/统筹)经前端UI演示完整协同链。后端业务逻辑质量尚可但有三重耦合债务:
1. 前端四端设定与后端固化为演示UI服务;
2. 心血管疾病(血压)硬编码渗透所有模块;
3. services/与collaboration/大面积拷贝,结构冗余。

改造后产出**通用住院协同Agent模块**(zhenhu namespace),核心逻辑无前端依赖,可对接臻护平台。

## 2. 核心改造(5条)

### 2.1 去四端设定 → Agent节点化
前端全部丢弃。后端保留的4个业务概念映射为LangGraph Agent节点:

| 原四端概念 | LangGraph节点 | 职责 |
|---|---|---|
| doctor_review | `doctor_review` | 查房前摘要、病程/沟通/出院草稿审核确认 |
| patient_confirm | `patient_confirm` | 家属承接反馈、生命体征录入、理解/执行异常上报 |
| execution_fallback | `execution_fallback` | 执行补位(再解释/无法执行/超时),必要时升级复核 |
| oversight_audit | `oversight_audit` | 只读闭环观察、积压/超时/异常信号聚合 |

### 2.2 去心血管硬编码 → 病种模板化
- `bp_entry` → `vital_sign_entry`,存储改为通用生命体征(key: value: unit:),血压仅为一种取值
- `bp_review_signal` → `vital_sign_alert`,阈值规则外置模板
- 病种差异全部JSON配置化(见§4模板格式),支持高血压/心衰/糖尿病

### 2.3 结构清洗:合并+namespace+中间件
- services/collaboration/ → 删除,原collaboration/保留并下移为domain/
- 添加 `src/zhenhu/` namespace包路径
- 挂载臻护中间件(审计、限流、trace-id注入)

### 2.4 Agent升级:Fixture → LangGraph StateGraph
```
入院采集(admission) → 风险分层(triage) → 持续监测(monitoring)
→ 出院准备(discharge) → 交接协同(handoff)
```
5节点 StateGraph,每节点通过 `knowledge-orchestrator` API 做RAG检索;保留原审核确认人工卡点;StateGraph不可变快照写入审计。

### 2.5 对接臻护:出院桥接+统一RAG
- 出院节点 `POST zhenhu-workflow-engine` 自动创建敏护病例
- 交接上下文序列化为FHIR CarePlan/MedicationRequest片段
- RAG统一走 `knowledge-orchestrator` 单一入口,不再直连KB

## 3. 目标结构

```
src/zhenhu/inpatient/
├── main.py                  # 模块入口,挂载router/middleware
├── models.py                # 28表→12表(去冗余/合并/通用化)
├── schemas.py               # Pydantic v2 请求/响应模型
├── agent/
│   ├── graph.py             # LangGraph StateGraph 定义
│   └── nodes.py             # 5 Agent节点实现
├── domain/
│   ├── handoff.py           # 交接协同(原collaboration/handoff)
│   ├── admission.py         # 入院流程(原collaboration/medical_history+review部分)
│   ├── monitoring.py        # 监测与提醒(原collaboration/bp_entry+signal)
│   └── templates.py         # 病种模板加载器
├── routes/
│   ├── admission.py         # POST /admission/start
│   ├── monitoring.py        # POST /monitoring/vital-sign
│   ├── discharge.py         # POST /discharge/prepare
│   └── admin.py             # GET  /admin/audit
├── hooks/
│   └── zhenhu_bridge.py     # 出院→workflow-engine, RAG→orchestrator
├── disease_templates/
│   ├── hypertension.json    # 高血压
│   ├── heart_failure.json   # 心衰
│   └── diabetes.json        # 糖尿病
└── legacy/                  # 归档原前后端(含前端dist/存根)
```

## 4. 病种模板JSON格式

```json
{
  "disease_id": "hypertension",
  "name": "高血压",
  "vital_signs": ["blood_pressure"],
  "risk_factors": ["age", "smoking", "family_history"],
  "monitoring_interval_hours": 4,
  "discharge_criteria": ["bp_stable_24h"],
  "handoff_instructions": ["用药方案", "居家血压监测", "复诊安排"]
}
```

## 5. 实施步骤

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| 1 | 建legacy/归档前后端,原Cardio不再演进 | git archive + 原路径改为只读 |
| 2 | 结构清洗:namespace+中间件+合并冗余 | pylint/mypy 零增量,2处重复代码消除 |
| 3 | 去硬编码:bp→vital_sign + 3套病种模板 | 模板JSON加载切换病种,原152测试全适配 |
| 4 | Agent框架搭建:LangGraph 5节点+Fixture→RAG | graph.py可独立单步调试,各节点->orchestrator链路通 |
| 5 | 对接臻护:出院节点POST bridge | workflow-engine收到CarePlan创建,集成测试通过 |
| 6 | 测试保持152+:全量回归 | pytest -q = 0 fail,新增integration agent用例≥10 |

---

> 全文约 750 字(含代码/表格)。实际改造顺序以臻护平台集成窗口与团队排期为准,方案路径为基线可裁剪。
