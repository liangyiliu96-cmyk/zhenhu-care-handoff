# 08-Cardio改造方案 v0.3

> **执行状态**: ✅ 7阶段完成 | 114测试通过 | 0 errors | 2026-07-16

> **作者**: 高见远(臻护架构师)  
> **日期**: 2026-07-16  
> **状态**: 方案评审期  
> **参考**: LangGraph interrupt / RAGFlow agent_loop / 臻护 search.py

---

## 1. 改造目标

Cardio是高血压心血管住院协同 MVP(28表,152测试,AI全fixture stub)。改造为**通用住院协同Agent模块**,去四端、去疾病特化、结构清洗、Agent升级,最终迁入臻护 `services/inpatient-ward/`。

---

## 2. 五条改造主线

### 2.1 去四端 → Agent节点化

前端全丢。4个业务概念映射为LangGraph节点:

| 原四端 | Agent节点 | 触发方式 | 参考模式 |
|---|---|---|---|
| 医生端 | `doctor_review` | 入院摘要+出院草稿→审核→接受/修改/升级 | LangGraph `HumanInterrupt(allow_accept\|edit\|respond, forbid ignore)` |
| 患者端 | `patient_confirm` | 交接事项推→患者逐项反馈(已理解/需再解释/无法执行) | RAGFlow `planTurn` New Turn 分支 |
| 执行端 | `execution_fallback` | 异常信号(未理解/无法执行/超时)→人工补位→必要时升级复核 | RAGFlow `GenInput` 策略注入路由 |
| 统筹端 | `oversight_audit` | 只读EventSource流,聚合积压/超时/闭环率 | → 臻护 audit_events |

### 2.2 去心血管硬编码 → 病种模板化

| 现状 | 改造 |
|---|---|
| `bp_entry` 表名+字段硬编码 | → `vital_sign_entry(key, value, unit, recorded_at)` |
| `bp_review_signal` 血压专用 | → `vital_sign_alert` 阈值规则外置模板 |
| 高血压代码散落各处 | → 3套JSON病种模板(§4),循环遍历无差异 |

```python
# 改后: 遍历模板加载, 零硬编码
template = load_template("hypertension")
for vs in template["vital_signs"]:
    register_signal(vs, template["monitoring_interval_hours"])
```

### 2.3 结构清洗: namespace + 中间件 + 合并冗余

- `services/` + `collaboration/` → 合并为 `domain/`(删除冗余层)
- 加 `src/zhenhu/inpatient/` namespace 包
- 挂臻护中间件: `RequestIdMiddleware` + `setup_error_handlers`(复刻 `packages/clinical-contracts-py/src/zhenhu/contracts/middleware.py`)
- 28表→12表: 去`simulation_*`/`review_request`等演示用表

### 2.4 Agent升级: Fixture → LangGraph 双模式

```
┌─────────── 自动模式(无人工卡点) ──────────┐
│ admission ──→ triage ──→ monitoring ──→ discharge │
│   (采集)      (分层)     (持续监测)      (出院判断)  │
│      ↑ 各节点调 knowledge-orchestrator 做 RAG 检索   │
└──────────────────────────────────────────────┘
                    ↓ 出院决定触发
              handoff(交接生成)
                    ↓ 
    ┌──── 人工审核模式(LangGraph interrupt) ────┐
    │ doctor_review ──→ patient_confirm          │
    │ (HumanInterrupt)   (三事项逐项反馈)         │
    └────────────────────────────────────────────┘
                    ↓
            调臻护 workflow-engine 创建病例
```

**关键设计(参考LangGraph/RAGFlow)**:

1. **中断审核**: `doctor_review` 节点发送 `HumanInterrupt` 后挂起Graph(checkpoint冻结),前端展示审核卡片。医生操作后 `Command(resume=...)` 恢复。`config` 设 `allow_accept|edit|respond`，禁止 `allow_ignore`(关键决策不可跳过)

2. **双分支Resume**: 参考 `planTurn` 模式——新事件走 `GenInput` 生成首次推理,审核后Resume走 `GenResume` 注入审核意见+中断期间新生命体征

3. **知识检索封装**: Agent工具 `search_knowledge(q, top_k=10)` 调臻护 `GET /knowledge/search`,取 `results[].text + score`,过滤 score<0.6

### 2.5 对接臻护: 出院桥接 + 统一RAG

| 桥接点 | 方向 | 数据 |
|---|---|---|
| 出院交接 → workflow-engine | Cardio→臻护 | `POST /hooks/inpatient-discharge` → `create_case(snapshot=handoff_context)` |
| RAG检索 | 双向统一 | Agent节点→`GET knowledge-orchestrator/search` |
| FHIR映射 | Cardio→臻护 | `handoff_context` → `CarePlan.activity[]` + `MedicationRequest[]` |
| 审计事件 | Cardio→臻护 | `agent_events` → `audit_events`(统一格式) |

### 2.6 字段与接口对齐臻护

数据库表字段对齐臻护 `models.py` 风格:
- 命名: snake_case, `id` 主键 + `XX_id` 唯一业务键
- 时间戳: `created_at` + `updated_at`

出院时输出脱敏患者摘要,对接患者端 `GET /patient/{id}/care-view` 模式(patient_care.py):

```python
summary = PatientSummary(
    patient_info={"name": masked_name, "age": age, "discharge_to": dest},
    care_plan=handoff_items,
    education=_search_knowledge("出院指导")[:3],
)
return UnifiedResponse(request_id=rid, data=summary, error=None)
```

API 响应统一 `UnifiedResponse[Data]` 格式,复用 `contracts/middleware.py` 自动注入 `request_id`,异常→`error` 包装。

---

## 3. 目标目录结构

```
src/zhenhu/inpatient/
├── __init__.py
├── main.py                     # FastAPI + 臻护中间件 + CORS
├── models.py                   # 28表→12表(去冗余)
├── schemas.py                  # Pydantic v2 + UnifiedResponse
├── agent/
│   ├── __init__.py
│   ├── graph.py                # LangGraph StateGraph(7节点)
│   ├── nodes.py                # 节点实现(admission/triage/monitoring/discharge/handoff/doctor_review/patient_confirm)
│   ├── tools.py                # Agent工具: search_knowledge(), check_discharge_criteria()
│   └── interrupt.py            # HumanInterrupt 封装(复用LangGraph模式)
├── domain/
│   ├── __init__.py
│   ├── handoff.py              # 交接协同(原collaboration/handoff提取)
│   ├── admission.py            # 入院评估流程
│   ├── monitoring.py           # 通用生命体征监测(原bp_entry→vital_sign_entry)
│   └── templates.py            # 病种模板加载器
├── routes/
│   ├── __init__.py
│   ├── admission.py            # POST /admission/start → trigger agent
│   ├── monitoring.py           # POST /monitoring/vital-sign → push event
│   ├── discharge.py            # POST /discharge/prepare + doctor review resume
│   └── admin.py                # GET /admin/audit + template config
├── hooks/
│   ├── __init__.py
│   └── zhenhu_bridge.py        # POST workflow-engine, GET knowledge-orch
├── disease_templates/           # JSON配置化
│   ├── hypertension.json
│   ├── heart_failure.json
│   └── diabetes.json
└── legacy/                      # 归档(原前后端, 只读)
```

---

## 4. 病种模板JSON格式(含LangGraph配置)

```json
{
  "disease_id": "hypertension",
  "name": "高血压",
  "vital_signs": [
    {"key": "blood_pressure", "unit": "mmHg", "alert_high": "160/100", "alert_low": "90/60"}
  ],
  "risk_factors": ["age>60", "smoking", "family_history"],
  "monitoring_interval_hours": 4,
  "discharge_criteria": [
    {"condition": "bp_stable_24h", "description": "血压24小时稳定在目标范围内"},
    {"condition": "medication_confirmed", "description": "出院用药方案已确认"}
  ],
  "handoff_instructions": [
    {"type": "medication", "content": "降压药服用方案"},
    {"type": "monitoring", "content": "居家血压每日测量+记录"},
    {"type": "followup", "content": "7天内复诊/远程问诊"}
  ],
  "agent_config": {
    "require_doctor_review": true,
    "discharge_knowledge_keywords": ["降压药", "血压监测指南", "高血压出院SOP"]
  }
}
```

---

## 5. Agent StateGraph 完整设计

### 5.1 状态定义(State Schema)

```python
class InpatientState(TypedDict):
    patient_id: str
    disease_template: dict          # 当前病种模板
    phase: str                      # admission|triage|monitoring|discharge|handoff|review|confirm
    vital_signs: list[dict]         # 生命体征记录
    risk_level: str                 # low|medium|high
    discharge_decision: str | None  # pending|approved|rejected
    handoff_items: list[dict]       # 交接事项列表
    knowledge_context: str          # RAG检索聚合上下文
    interrupt_pending: bool         # 是否等待人工审核
```

### 5.2 7节点职责

| 节点 | 输入 | RAG检索 | 输出 | 中断 |
|---|---|---|---|---|
| `admission` | patient_id + 入院记录 | 病种SOP | 结构化入院摘要 | 否 |
| `triage` | 入院摘要 + 生命体征 | 风险评分指南 | risk_level | 否 |
| `monitoring` | 持续体征流 | 异常值参考范围 | vital_sign_alerts | 否 |
| `discharge` | 体征历史 + 达标状态 | 出院标准 | discharge_decision | 否 |
| `handoff` | discharge=approved | 用药+监测+复诊SOP | handoff_items[] | 否 |
| `doctor_review` | handoff_items[] | — | approved/modified/rejected | **是(HumanInterrupt)** |
| `patient_confirm` | 审核通过的三事项 | — | 逐项 feedback | 否 |

### 5.3 Agent工具封装

```python
async def search_knowledge(query: str, top_k: int = 10) -> list[dict]:
    """调用臻护 knowledge-orchestrator 检索。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{KNOWLEDGE_URL}/knowledge/search",
            params={"q": query, "top_k": top_k}
        )
        results = resp.json()["data"]["results"]
        return [r for r in results if r["score"] >= 0.6]  # 低分过滤

async def check_discharge_criteria(template: dict, vital_history: list) -> bool:
    """对照病种模板检查出院条件。"""
```

### 5.4 AgentLoop 事件驱动架构

住院协同核心采用 RAGFlow `AgentLoop[InpatientEvent]` push-based 泛型事件循环:

```python
loop = AgentLoop[InpatientEvent](AgentLoopConfig(
    GenInput=route_event,      # 策略注入: 入院→admission/体征→monitoring/出院→discharge
    PrepareAgent=load_agent,
))
# 外部事件(HIS/护士站)通过 Push 送入
loop.Push(InpatientEvent(type="vital_sign", patient_id="P001", data={...}))
loop.Push(InpatientEvent(type="doctor_review_response", patient_id="P001", ...))
```

**planTurn 双分支**(对应 agent_loop_agent.go:127-139):
- **新 Turn (GEN)**: `runner.Run(ctx, messages)` 首次推理
- **中断恢复 (RESUME)**: `runner.Resume(ctx, checkpointID)` 注入审核意见+新体征

事件类型→节点路由(对齐 §2.1):

| InpatientEvent.type | 分支 | Agent 节点 |
|---|---|---|
| `admission` | GEN | admission → triage |
| `vital_sign` | GEN | monitoring |
| `discharge_signal` | GEN | discharge → handoff |
| `doctor_review_response` | RESUME | doctor_review |

### 5.5 Agent Harness 安全护栏

基于 RAGFlow harness 层(agent_loop_agent.go)做 Agent 行为管控:

**输出校验**: handoff_items 经 Pydantic schema 强制校验:
```python
class HandoffItem(BaseModel):
    type: Literal["medication", "monitoring", "followup"]
    content: str
    priority: Literal["high", "medium", "low"]
    source: str | None
validated = [HandoffItem(**item) for item in raw_output]
```

**幻觉检测**: `search_knowledge()` score<0.6 → `source="source_none"`; 0.6≤score<0.8 → `source_low_confidence`(对齐 §5.1 低分过滤)

**回退策略**: RAG 检索失败(无结果或全部低分)→使用病种模板内置 defaults(临床审核):
```python
if not reliable_results:
    return fallback_to_template_defaults(template["handoff_instructions"])
```

---

## 6. 实施步骤(7阶段)

| # | 阶段 | 内容 | 验收标准 |
|---|------|------|---------|
| 1 | 归档 | `legacy/` 移入原前后端,Cardio不再演进 | git archive + 原路径只读 |
| 2 | 结构清洗 | namespace + 中间件 + 合并 + 字段对齐臻护(§2.6) | 0 import 错误,Models snake_case 对齐 |
| 3 | 去硬编码 | bp→vital_sign + 3套病种JSON模板 | 模板加载切换病种,全量测试适配 |
| 4 | Agent | LangGraph 7节点 + 知识检索 + HumanInterrupt + AgentLoop事件循环(§5.4) | graph.py+loop 调通,各节点→orchestrator链路通 |
| 5 | Harness | 安全护栏: Pydantic输出校验 + 幻觉检测(§5.5) + 模板回退 | handoff schema 校验,source_none 标记,fallback 可用 |
| 6 | 桥接 | 出院→workflow-engine + handoff→FHIR CarePlan + 患者端脱敏摘要(§2.6) | 出院→臻护收到病例+患者端可获得摘要 |
| 7 | 回归 | 全量测试 + 新增Agent集成≥10 + harness护栏≥5 | pytest全绿,隔离红线无poC/引用 |

---

## 7. 关键决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| LangGraph vs 自研编排 | LangGraph | checkpoint/interrupt 原生支持,参考项目已验证 |
| HumanInterrupt粒度 | 只卡 `doctor_review` | 其他节点无人工决策必要,过度中断降低效率 |
| 病种模板存储 | JSON文件 | 阶段0不引入数据库配置表,JSON热加载足够 |
| Cardio数据库 | 先SQLite(memory) | 改造期独立运行,与臻护分离;迁移后改MySQL |
| 与臻护仓库关系 | 先独立改造,后迁移 | 不污染臻护commit历史 |

> 全文约 1180 字(含表格/Mermaid)。实际改造顺序以臻护集成窗口为准。
