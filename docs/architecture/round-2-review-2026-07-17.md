# 臻护出院交接平台 — 第二轮架构审查与发展优化分析

> 审查日期：2026-07-17 23:30 | 审查人：系统架构师 | 基准：Round 1 (7.5/10) → Round 2

---

## A. 更新架构健康度评分

| 维度 | Round 1 | Round 2 | Δ | 说明 |
|------|:------:|:------:|:---:|------|
| **1. 模块边界** | 7.0 | **8.5** | +1.5 | 三卡点独立、LLM工具层独立、config单一事实源 |
| **2. 代码复杂度** | 6.5 | **8.0** | +1.5 | nodes_clinical 848→497行(-42%)，prompt集中到17函数 |
| **3. 依赖关系** | 7.0 | **8.0** | +1.0 | `_cached_provider` 副本 4→1处(P1-2)，仍有2处get_ai_provider遗漏 |
| **4. LLM 集成** | 5.5 | **8.5** | +3.0 | 最大改善：prompt集中管理+成本追踪+provider统一 |
| **5. 新增模块质量** | — | **8.0** | — | llm_utils/prompts/nodes_checkpoints 设计合理，各有边界 |

### 整体评分：**8.0 / 10**（+0.5）

---

### A1. 模块边界 — 更清晰

拆分后形成 4 层 15 文件的清晰结构：

```
agent/
├── 配置层    config.py                ← 环境变量 + get_cached_provider() 唯一事实源
├── 工具层    llm_utils.py             ← safe_llm_invoke / 缓存 / DDxItem / 成本追踪
│            prompts.py               ← 17个prompt构建函数，按6个临床阶段分类
├── 编排层    graph.py                 ← StateGraph + InpatientState + validate_state
│            loop.py                  ← PatientAgentLoop + 并发锁
│            nodes.py                 ← 兼容聚合入口(纯re-export)
├── 节点层    nodes_admission.py       ← 入院/分诊/用药核对
│            nodes_clinical.py         ← 病史/PE/DDx/护理/交班 (497行)
│            nodes_checkpoints.py      ← 三卡点: doctor_confirm/med_confirm/discharge_sign
│            nodes_handoff.py          ← 出院/交接/审核/确认
│            nodes_monitoring.py       ← 监测/查房/调药/检验/转科
│            nodes_scoring.py          ← 临床评分(NEWS2/qSOFA/VTE/STK/MDT/Padua)
├── 领域对象  assessments.py, medication_rules.py, fhir_sync.py
├── 基础设施  persistence.py, metrics.py, harness.py, interrupt.py, tools.py
```

**评价**：工具层 (`llm_utils` + `prompts`) 的建立是最大结构性改善——节点文件不再混杂 LLM 调用细节和 prompt 字符串，只关注临床业务编排。

---

### A2. 代码复杂度 — 热点缓解

| 文件 | Round1 | Round2 | 变化 |
|------|:------:|:------:|------|
| `nodes_clinical.py` | 848 | 497 | **-42%** ✅ |
| `nodes_checkpoints.py` | — | 200 | 新增，独立性强 |
| `llm_utils.py` | — | 145 | 新增，职责纯粹 |
| `prompts.py` | — | 287 | 新增，可读性高 |
| `graph.py` | 426 | 557 | +131(validate_state 校验层) |
| `config.py` | ~35 | 60 | +25(provider 缓存) |

**评价**：热点文件 `nodes_clinical` 从超800行下降到500行以下。graph.py 增长是 validate_state 55字段校验层的附加，属于有意义的复杂度。

---

### A3. 依赖关系 — 显著改善

**Round 1 核心问题**：4 个节点文件各有独立 `_cached_provider()` 副本。

**Round 2 状态**：✅ 已统一到 `config.get_cached_provider()`。5个节点文件（admission/clinical/handoff/monitoring/tools）全部通过 `from .config import get_cached_provider` 引用。

**新发现遗漏**：
- `nodes_scoring.py` 的 NEWS2 建议（L192）和 qSOFA 建议（L259）仍直接调用 `get_ai_provider()`，未走缓存——**P1-2 未完全覆盖 scoring 文件**
- `nodes_clinical.py:485` 的 `node_shift_summary` 也直接 `get_ai_provider()` 而非 `get_cached_provider()`

**Import 依赖图（更新后）**：
```
llm_utils.py → (无项目内依赖，仅标准库+pydantic)        ← 最底层
prompts.py → (无项目内依赖，仅 json)                     ← 最底层
config.py → zhenhu.contracts.agent (lazy import)           ← 配置层
nodes_*.py → config + llm_utils + prompts + metrics        ← 节点层
graph.py → nodes_*.py + config                             ← 编排层
loop.py → graph.py + config                                ← 编排层
```

无循环依赖，依赖方向明确：工具→配置→节点→编排。

---

### A4. LLM 集成 — 本批次最大改善

| 子维度 | Round 1 | Round 2 |
|--------|---------|---------|
| Prompt 管理 | 25+ 内联字符串散落5文件 | 17函数集中在 `prompts.py`，6阶段分类 |
| Provider 缓存 | 4处独立副本 | 1处 `config.get_cached_provider()` |
| 成本追踪 | 无 | 7维度计数器 (`total_calls/success/cache_hits/timeouts/errors/latency/chars`) |
| LLM 工具层 | 与节点代码混杂 | `llm_utils.py` 独立: safe_llm_invoke + 缓存 + DDxItem |
| 调用防护 | 超时+重试 | 超时+重试+缓存+指标，全部统一入口 |

**prompts.py 设计评价**：17个函数按入院期(5)/鉴别诊断(2)/监测期(3)/交接期(4)/评分(2)/用药(1)六个临床阶段分类，函数签名明确参数类型，节点层只需调用 `prompts.xxx_prompt(...)` 即可。可维护性和可测试性大幅提升。

---

### A5. 新增模块质量分析

| 模块 | 行数 | 设计评价 | 关注点 |
|------|:---:|------|------|
| `llm_utils.py` | 145 | ⭐⭐⭐⭐⭐ 职责纯粹，`safe_llm_invoke`+`cache_get/set`+`DDxItem`+成本追踪四合一，是所有节点文件的唯一 LLM 交互入口 | 缓存上限200条+30min TTL对长租户可能不足 |
| `prompts.py` | 287 | ⭐⭐⭐⭐ 函数化清晰，但每个函数参数数量偏多(5-11个)，可考虑用 dataclass 收敛 |
| `nodes_checkpoints.py` | 200 | ⭐⭐⭐⭐ 三卡点独立性强，幂等守卫+自动降级+`pending_review` 构造完整。`_get_abnormal_labs()` 是纯工具函数，位置合理 | 三卡点 `payload` 构造有15-20%结构重复（都包含 `patient_id`+`template`+`vital_trend`），可提取公共构造器 |

---

## B. 遗留技术债务 — 状态更新

### B1. 已完成的债务（全部 9 项 P0/P1/P2）

| ID | 项目 | 状态 | 验证证据 |
|----|------|:---:|------|
| P0-1 | 双engine统一 | ✅ | `models.py:416-417` 注释确认删除冗余 engine，`init_db()` 通过 lazy import 引用 `main.async_engine` |
| P0-2 | state_store后台清理 | ✅ | `state_store.py:3` daemon 线程 5min 清理 + `/metrics` 暴露 |
| P0-3 | state运行时校验 | ✅ | `graph.py:431-557` `validate_state()` 55字段自动修复+`_STATE_DEFAULTS` 完整映射 |
| P1-1 | Prompt集中管理 | ✅ | `prompts.py` 17函数, 6阶段分类, 5文件接入 (clinical/admission/monitoring/handoff/scoring) |
| P1-2 | provider缓存统一 | ⚠️ | 4节点文件+tool统一，但 **scoring/clinical 各有1处遗漏**（见下B2） |
| P1-4 | 文件拆分 | ✅ | `nodes_clinical` 848→497行(-42%), `llm_utils.py` + `nodes_checkpoints.py` 独立 |
| P1-5 | persistence SQLite | ✅ | WAL 模式, `INSERT OR REPLACE`, 文件 fallback |
| P2-1 | LLM成本追踪 | ✅ | `llm_utils.py:21-55` 7维度指标, `get_llm_metrics()` 公开接口 |
| P2-2 | 评分阈值外置 | ✅ | `scoring_thresholds.yaml`, 懒加载 `_load_thresholds()`, 硬编码 fallback |

### B2. 仍需关注的债务

| ID | 问题 | 当前状态 | 优先级 | 建议 |
|----|------|------|:---:|------|
| **P1-2-遗漏** | `nodes_scoring.py:192` 和 `nodes_scoring.py:259` 直接用 `get_ai_provider()` 不走缓存 | 🔴 新发现 | P1 | 改为 `from .config import get_cached_provider` |
| **P1-2-遗漏** | `nodes_clinical.py:485` (`node_shift_summary`) 直接用 `get_ai_provider()` | 🔴 新发现 | P1 | 同上 |
| **P1-3** | 路由层绕过领域层 | ⚠️ 未动 | P1 | `review.py` 仍直接操作 state dict |
| **P2-3** | 26 个路由文件 | ⚠️ 未动（反增1个） | P2 | 仍可合并 `lab_trends+vital_trends→trends` |
| **P2-4** | 路由层无独立测试 | ⚠️ 未动 | P2 | 测试仍集中在 agent 节点 |
| **新-P3** | `prompts.py` 函数参数膨胀 | 🟡 hpi_prompt(3参数)到 daily_round_prompt(11参数) | P3 | 可引入 PromptContext dataclass |
| **新-P3** | `validate_state` 55字段与 `default_state` 需同步维护 | 🟡 两处独立定义 | P3 | 可从 `_STATE_DEFAULTS` 自动生成 `default_state()` |

### B3. 状态一致性问题 — 更新

| 风险 | Round 1 状态 | Round 2 状态 |
|------|:---:|:---:|
| 部分写入 | 🟡 中 | 🟡 中（无变化，LangGraph 原生限制） |
| TTL 过期丢失 | 🟡 中 | 🟢 **降低** — `persistence.py` SQLite 持久化兜底 |
| 幂等守卫 | 🟡 中 | 🟢 **降低** — 三卡点幂等守卫完善 + LLM 缓存防 resume 重算 |

---

## C. 下一步发展建议

### 推荐投入的 5 个方向

| # | 方向 | 难度 | 预期收益 | 理由 |
|---|------|:---:|:---:|------|
| **1** | **P1-2 收尾：消除最后 3 处 `get_ai_provider()` 直接调用** | 🟢 低 | 中 | 10分钟工作量，完成 provider 缓存统一化的最后拼图。`nodes_scoring.py` 2处 + `nodes_clinical.py:485` 1处 |
| **2** | **路由层解耦：增加 `agent/service.py` 门面** | 🟡 中 | 🔴 高 | 当前 26 个路由文件直接操作 state dict + 调 loop，换 Agent 框架代价大。service 层封装 `gen_input/plan_turn/resume` 可显著降低耦合 |
| **3** | **路由文件合并：按临床域收敛** | 🟡 中 | 🟡 中 | 26→~15 文件: `lab_trends+vital_trends→trends`, `ward_overview+ward_priority→ward`, `clinical_note+nursing→nursing_board`, `command+review→doctor_actions` |
| **4** | **路由层 API 契约测试** | 🟡 中 | 🔴 高 | 当前 112 tests 全在 agent 层，路由重构无安全网。建议先加 8-10 个核心端点 smoketest（admission/monitoring/discharge/review/command/rounds/dashboard/scores） |
| **5** | **prompts.py 参数收敛：PromptContext dataclass** | 🟢 低 | 🟡 中 | 当前 `daily_round_prompt` 11参数、`discharge_orders_prompt` 7参数，函数签名冗长。引入 dataclass 可同时改善可读性和 A/B 测试能力 |

### 不建议立即投入的方向

- **Redis 替换 state_store**：当前并发量下内存存储足够，且 persistence SQLite 已解决 pending_review 跨进程问题
- **Docker 化**：部署层工作，不应在架构迭代期分散精力
- **微服务拆分**：拆分评分引擎/LLM网关等需要先完成 P1-3 路由解耦，否则拆分会导致更多耦合面

---

## D. 架构健康度趋势图

```
Round 1 (7.5)  ──→  Round 2 (8.0)  ──→  目标 (8.5+)

已完成:                                  待完成:
✅ 双engine统一 (P0-1)                   ⬜ 路由层解耦 (P1-3)
✅ 状态清理+校验 (P0-2/P0-3)             ⬜ 路由文件合并 (P2-3)
✅ Prompt集中管理 (P1-1)                 ⬜ 路由层测试 (P2-4)
✅ Provider统一 (P1-2, 95%)              ⬜ P1-2 收尾3处遗漏
✅ 文件拆分 (P1-4)
✅ 持久化升级 (P1-5)
✅ 成本追踪 (P2-1)
✅ 阈值外置 (P2-2)
```

---

## E. 代码质量总结

### 亮点（继承 + 新增）
- ✅ Agent 编排优雅（StateGraph 19节点 + 条件路由，无退化）
- ✅ LLM 工具层设计优秀（`llm_utils.py` + `prompts.py` 是本次最大架构收益）
- ✅ 文件拆分效果显著（`nodes_clinical` 减42%，三卡点独立清晰）
- ✅ 线程安全持续成熟（3级锁 + daemon清理 + WAL 持久化）
- ✅ 测试 112/112 全绿，架构变更后无回归
- ✅ 配置外置起步（scoring_thresholds.yaml 模式可推广到其他配置）

### 改进空间
- ⚠️ P1-2 有 3 处 `get_ai_provider()` 遗漏（scoring 2处 + clinical 1处）
- ⚠️ 路由层 26 文件仍过度耦合，P1-3 未启动
- ⚠️ 路由层无测试，重构安全网缺失
- ⚠️ `prompts.py` 部分函数参数偏多，可引入 dataclass

### 与其他服务的对比（更新）

| 维度 | inpatient-ward | workflow-engine | knowledge-orchestrator | fhir-adapter |
|------|:---:|:---:|:---:|:---:|
| 代码规模 | 9,307行 | ~2,500行 | ~3,000行 | ~1,500行 |
| 复杂度 | 🔴 高 (19节点+55字段) | 🟡 中 | 🟡 中 | 🟢 低 |
| LLM 工程化 | ✅ 完善 (工具层+prompt管理+成本追踪) | ❌ 无 | ✅ 混合检索 | ❌ 无 |
| 架构成熟度 | 🟡→🟢 本批次大幅提升 | ✅ 成熟 | ✅ 成熟 | 🟢 |
| 测试覆盖 | 112/112 全绿 | ~30 | ~25 | ~15 |

**结论**：Round 2 架构成熟度从 7.5→8.0，LLM 工程化是本批次最大亮点。路由层解耦是下一优先级。P1-2 的 3 处遗漏应作为快速收尾优先修复。
