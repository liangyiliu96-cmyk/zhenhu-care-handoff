# 臻护住院协同 — R3 架构审查与发展优化分析

**日期**: 2026-07-18  
**基线**: 130/130 测试通过 | ~12,045 行 (src 10,088 + tests 1,957) | 18 病种 × 12 科室 | 19 节点 StateGraph  
**审查人**: 系统架构师 高见远

---

## A. 工业落地维度

### A1. 生产就绪度评估

| 维度 | 状态 | 证据 | 差距 |
|------|------|------|------|
| **核心流程完整性** | ✅ 已达标 | admission→discharge 全链路 19 节点，3 个医生卡点，per-patient lock (loop.py L192-194) | — |
| **状态持久化** | ⚠️ 部分达标 | Memory dict `_store` + TTL 30min (state_store.py L15)，无外部存储 | 进程重启丢失所有患者状态 |
| **熔断与降级** | ✅ 已达标 | CircuitBreaker (harness.py L91)，LLM 回退 RuleBasedProvider (main.py L68-70) | — |
| **并发安全** | ✅ 已达标 | threading.Lock (state_store.py L13) + per-patient asyncio.Lock (loop.py L197-203) | — |
| **数据持久化** | ✅ 已达标 | SQLAlchemy async engine + SQLite/PostgreSQL (main.py L73-87) | — |
| **测试覆盖** | ✅ 已达标 | 130 tests: 11 文件覆盖 agent, integration, routes, endpoints | 缺少性能/压力测试 |

**结论**: Demos 可用，单实例可试点。生产需解决 state_store 持久化和鉴权。

### A2. 鉴权 — 需要升级

**当前**: `x-role: doctor|nurse` 明文头 (middleware/auth.py L40-71)

**问题**:
- 无身份验证（任何人都可伪造 header 为 `doctor`）
- 无 token 过期/刷新机制
- 默认 `doctor` 角色 (L58)：未发送 header 时获得最高权限
- 路径前缀匹配 (`startswith`) 过于粗糙，`/review/` 同时也匹配 `/reviews/`

**升级路径** (按优先级):
1. **Phase-1 (本周可做)**: 迁移到 `zhenhu.contracts` 共享 JWT 中间件，使用 HS256 + 角色声明
2. **Phase-2**: 引入 OAuth2 Password Flow / API Key（若对接 HIS 系统）
3. **生产**: RBAC 细粒度（`doctor:cardiology`, `nurse:icu`），科室级隔离

**为何不选**: Basic Auth — 无过期机制，密码泄露风险高。mTLS — 对前端不友好。

### A3. 可观测性

**当前**: `metrics.py` 提供自定义 Prometheus 端点 `/metrics` (main.py L204-226)，含节点调用、turn 延迟、LLM 成本。

**差距**:
- 无结构化日志（当前是 `logging.basicConfig` 纯文本，main.py L55）
- 缺 HTTP 中间件级指标（请求数、状态码分布、延迟分位数）
- 无 trace 传播（虽然有 `X-Request-ID` 中间件但未关联 metrics）
- 无告警规则定义

**最低可行升级**:
1. 添加 `prometheus-fastapi-instrumentator` 自动收集 HTTP 指标
2. 结构化日志 → JSON 格式 (python-json-logger)
3. 定义 3 条关键告警:
   - `zhenhu_turn_failed_total` 5 分钟增量 > 5 → P1
   - `zhenhu_turn_avg_latency_ms` > 30s → P2
   - `zhenhu_state_store_entries` > 500 → P2 (内存压力)

### A4. 配置管理

**当前**: `os.getenv()` 分布在 `config.py` (集中) 和 `main.py`/`persistence.py` (分散)。

**问题**:
- `.env` 曾含 API key 明文（已脱敏并应通过部署环境注入）
- 无配置校验 (启动时不检查必填项)
- 无配置热更新（改环境变量需重启）

**建议**: 当前阶段 `config.py` + 环境变量足够。生产前引入 `pydantic-settings` 做启动时校验。**不引入配置服务**（12 个配置项不值得引入 etcd/consul 的运维复杂度）。

### A5. 部署 — Docker 化优先级

`pyproject.toml` 已定义依赖，无 Dockerfile。建议顺序:

1. **P0**: 添加 `Dockerfile` (python:3.12-slim + uvicorn)
2. **P1**: `docker-compose.yml` (app + 可选 PostgreSQL)
3. **P2**: 健康检查 `/health` 已就绪 (main.py L187)，可直接用于 k8s liveness probe

### A6. API 成熟度

| 维度 | 评估 | 证据 |
|------|------|------|
| **统一响应** | ✅ | `UnifiedResponse(data=...|error=...)` 全局使用 |
| **错误码** | ⚠️ | 仅有 `NOT_FOUND` 硬编码字符串，无枚举定义 |
| **版本化** | ❌ | 无 `/v1/` 前缀，无 API version header |
| **OpenAPI 文档** | ✅ | FastAPI 自动生成 `/docs` |
| **输入校验** | ✅ | Pydantic v2 models (route_schemas.py) |
| **分页** | ❌ | `/ward/overview` 等列表端点无分页 |

**需要修复**: 定义 `ErrorCode` 枚举替代硬编码字符串；列表端点加分页。

---

## B. 临床实用维度

### B1. 临床流程完整性

19 节点覆盖 admission → discharge 全链路:

```
admission → history_taking → PE → DDx → med_recon → triage
  → doctor_confirm(①) → Padua → VTE → monitoring
  → NEWS2 → qSOFA → MDT → [路由]
  → daily_round → nursing → shift_summary → lab_review → monitoring(循环)
  → stroke_antithrombotic → doctor_discharge_sign(③) → handoff → review → patient_confirm
```

**临床价值评估**:
- ✅ 入院链: history_taking + PE + DDx 符合 SOAP 标准
- ✅ 监测环: NEWS2/qSOFA/Padua 三个国际评分 → 临床决策支撑充分
- ✅ 三卡点: 入院确认/调药确认/出院签字 → 符合医疗安全要求
- ⚠️ 缺失: 无 MDT 会诊实质流程 (仅 `mdt_trigger` 节点触发条件路由，无会诊内容)
- ⚠️ 缺失: 无患者教育/知情同意节点

### B2. 模板质量

抽样分析 4 个模板 (heart_failure, pneumonia, diabetes, sepsis):

| 模板 | vital_signs | discharge_criteria | complication_monitoring | 临床评价 |
|------|-------------|-------------------|------------------------|---------|
| heart_failure | 10 项 (含 NT-proBNP/JVP/尿量) | 5 项具体标准 | 有 | ⭐⭐⭐⭐ 内容充实，NT-proBNP 阈值合理 |
| pneumonia | 5 项 (SpO2/T/RR/HR/BP) | 5 项 (含 CRP/X-ray) | 有 | ⭐⭐⭐⭐ CURB-65 相关标准覆盖 |
| diabetes | 7 项 (血糖/血压/HbA1c/酮体/K+) | 有 | 有 | ⭐⭐⭐⭐ 酮症酸中毒标志物到位 |
| sepsis | — | — | 4 并发症 (休克/ARDS/AKI/DIC) | ⭐⭐⭐⭐⭐ 最佳并发症监测 |

**共性问题**:
- 18/18 模板均有 `complication_monitoring` (grep 确认)
- 出院标准大多是定性描述 (如 `clinical_euvolemia_24h`)，缺少可量化阈值
- 部分风险因子无可执行匹配器 (如 `ef<40%`, `nyha_class_iii_iv` 未在 `_RISK_FACTOR_MATCHERS` 中定义)

**建议**: 为高频病种 (HF, COPD, stroke) 的出院标准补量化阈值 (如 "体重稳定±0.5kg×2天")。

### B3. 告警有效性

**去重机制**: `validate_state()` (graph.py L573-591) 基于签名前缀去重 + 保留最近 50 条。`dedup_clinical_alerts()` (harness.py L263-302) 以告警类型前缀 `[XXX]` 做全量去重。

**漏报风险**: **存在的**。`dedup_clinical_alerts()` 的 `_signature()` 取 `[XXX]` + 前 15 字符，若同一并发症的不同表现产生相同前缀但不同内容，会被错误去重。例如:
- `[并发症] 急性呼吸衰竭 预警: SpO2<88%` → sig = `[并发症]急性呼吸衰竭 预警: SpO2<88%`
- `[并发症] 急性呼吸衰竭 预警: PaCO2>50` → sig = `[并发症]急性呼吸衰竭 预警: PaCO2>50`

这里前缀不同所以会保留——**实际上没问题**。真正的风险在于: `suppress_window=3` 轮后如果同样条件再次触发，不会再告警（但这是设计意图，防止告警疲劳）。

**结论**: 去重逻辑合理，不会导致临床意义上的漏报。

### B4. 并发症检测

`_check_complication_watch()` (nodes_monitoring.py L20-45) 每轮监测检查所有 watch 条件。

**命中率分析**:
- 量化条件 (如 `SpO2<88%`) — 通过正则 `re.match(r'([A-Za-z\d\u4e00-\u9fff]+)\s*([><])\s*([\d.]+)', watch)` 解析 — 命中率高
- 非量化条件 (如 `辅助呼吸肌参与`, `广泛出血倾向`) — 走 `sign_val` 字符串匹配 — **几乎不会命中**，因为 `vital_signs` 中的值通常是数值，不存在 `"辅助呼吸肌参与"` 这样的字符串值
- 检验项模糊匹配 (L101-103) — `lab_name in watch` 只要存在就返回 True，**过于宽松**（如 WBC 在任何 watch 中出现都会触发）

**建议**: 非量化条件改为 LLM 辅助判断或从 watch 列表中移除（它们目前是"死代码"）。

### B5. LLM 使用评估

识别到 LLM 调用的节点:

| 节点 | LLM 用途 | 必要性 | 替代方案 |
|------|---------|--------|---------|
| node_history_taking | HPI 叙事生成 | ✅ 必要 | — (叙事段落需要 NLG) |
| node_physical_exam | PE 叙事生成 | ✅ 必要 | — |
| node_ddx | 鉴别诊断排序 | ✅ 必要 | — |
| node_nursing | 护理措施补充 | ⚠️ 可替代 | 科室清单 `_DEPT_CHECKLIST` 已覆盖 12 科室 |
| node_shift_summary | 交班摘要 | ⚠️ 可替代 | 模板填充 (患者状态 + 关键事件列表) |
| node_daily_round | SOAP 生成 | ✅ 必要 | — |
| node_discharge | 出院医嘱 | ✅ 必要 | — (需个性化) |
| node_handoff | 交接事项 | ⚠️ 可替代 | 模板 `handoff_instructions` 已定义 |

**建议**: `node_nursing` 和 `node_shift_summary` 的 LLM 调用可改为 rules-first（先用 `_DEPT_CHECKLIST` + 模板，LLM 仅作为 fallback），可减少 30-40% LLM 调用量。

---

## C. 架构风险

### C1. 跨层依赖 (agent → routes import _DEPT_CHECKLIST)

**位置**: `nodes_clinical.py:395` → `from ...routes.nurse_board import _DEPT_CHECKLIST`

这是**架构分层违规**: agent 层不应依赖 routes 层。当前能工作是因为:
- `_DEPT_CHECKLIST` 是纯数据常量 (dict)，无副作用
- import 被包在 try/except ImportError 中

**修复方案**: 将 `_DEPT_CHECKLIST` 提取到 `agent/constants.py` 或 `domain/` 层，routes 和 agent 都从那里导入。这是最小代价的修复。

### C2. harness ↔ nodes_admission 循环依赖

**路径**: `harness.py → nodes_admission.load_template` (L116, L243), `nodes_admission.py → harness.normalize_template` (L15)

这是**函数级调用**而非模块级循环导入 (都是函数内 delay import)，所以运行时可行。但逻辑上是循环依赖:
- harness 的 `merge_comorbidity_template` 和 `detect_department_mismatch` 调用 nodes_admission 的 `load_template`
- nodes_admission 的 `load_template` 调用 harness 的 `normalize_template`

**风险**: 中等。如果未来 `load_template` 也需要 `merge_comorbidity_template`，将形成真正的循环。

**推荐**: 将 `normalize_template` 移到 `tools.py` 或新建 `template_utils.py`，两边都从那里导入。

### C3. state_store 容量

**当前**: `_store: dict[str, tuple[float, dict]]` 纯内存 (state_store.py L15)，TTL 30min。

**130 患者测试**: 假设每患者 state dict ~5KB (含 50+ 字段的序列化数据)，130 × 5KB = 650KB 内存，完全可接受。

**生产预估**: 300 床位医院，峰值 150 活跃患者 → ~750KB。**当前设计无容量问题**。后台清理线程 (L54) 每 5 分钟清理过期条目。

**真正风险**: 进程重启全部丢失。需引入 Redis 或 SQLite 持久化 state_store。

### C4. validate_state 每轮开销

`validate_state()` (graph.py L515-592) 在 `plan_turn` (loop.py L112) 和 `gen_input` (loop.py L56-63) 入口执行。每轮遍历 64 个字段做类型检查。

**开销分析**: 64 × O(1) 字典操作 ≈ 微秒级。即使每秒 100 turns 也是可忽略的。**无性能问题**。

**告警去重部分** (L573-591): 对 `clinical_alerts` 做 O(n²) 签名遍历。当 alerts 累积到 50+ 时，每次去重扫描 50 × N 次比较。考虑到目前告警上限 50 条，仍在可接受范围。

---

## D. 下一步路线图

按优先级排序 (结合工业落地和临床价值):

### P0 — 本周必须做 (阻塞试点)

| # | 方向 | 理由 | 工作量 |
|---|------|------|--------|
| 1 | **鉴权升级**: x-role header → JWT (zhenhu.contracts 共享中间件) | 明文 header 在生产不可接受；默认 doctor 是安全漏洞 | 2-3d |
| 2 | **跨层依赖修复**: `_DEPT_CHECKLIST` 提取到 `agent/constants.py` | 架构分层违规，影响可维护性 | 0.5d |

### P1 — 本月应做 (试点前)

| # | 方向 | 理由 | 工作量 |
|---|------|------|--------|
| 3 | **state_store 持久化**: Redis 或 SQLite 替代纯内存 dict | 进程重启丢状态不可接受；现有 persistence.py 的 SQLite 模式可复用 | 3-5d |
| 4 | **LLM 优化**: nursing/shift_summary 改 rules-first，LLM fallback | 减少 30-40% LLM 调用 → 降成本 + 提速 | 2-3d |
| 5 | **API 补齐**: 错误码枚举 + 分页 + `/v1/` 前缀 | API 成熟度从 demo 级提升到 production 级 | 1-2d |

### P2 — 下季度

| # | 方向 | 理由 |
|---|------|------|
| 6 | **模板临床深化**: 出院标准量化 + 非量化 watch 条件替换 | 提升并发症检测命中率 |
| 7 | **可观测性升级**: JSON 结构化日志 + HTTP metrics + 告警规则 | 运维必备 |
| 8 | **Docker 化 + docker-compose**: 一键部署 | 降低试点部署门槛 |

---

## 总结评分

| 维度 | R2 评分 | R3 评分 | 变化 |
|------|---------|---------|------|
| 代码质量 | 8.0 | 8.5 | ↑ 拆分节点文件 + QA 修复 |
| 临床深度 | 7.0 | 8.0 | ↑ 并发症检测 + 科室差异化 |
| 架构整洁 | 7.5 | 7.0 | ↓ 新增跨层依赖 |
| 生产就绪 | 5.0 | 6.5 | ↑ 熔断/去重/auto-cleanup |
| **综合** | **8.0** | **8.0** | 持平 — 临床功能增加但架构债抵消 |

**一句话**: R3 在临床实用性上显著进步 (并发症 watch、科室清单、出院 QA)，但引入了跨层依赖 (agent→routes) 这个架构债。修复后可达 8.5。
