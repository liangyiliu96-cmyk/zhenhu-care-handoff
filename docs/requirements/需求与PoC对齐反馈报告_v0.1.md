# 需求与 PoC 对齐反馈报告 v0.1

**对齐对象：** 《AI 出院交接与慢病随访协同平台 需求规格说明书 v0.2》、《需求证据基线与待确认清单 v0.1》 ↔ 当前 PoC 实现与文档
**生成日期：** 2026-07-15
**性质：** 双向对齐反馈。正向修订 PoC 滞后文档使其对齐需求；反向标注需求侧事实性滞后与设计性含糊。本轮**不写正式项目代码**。

## 1. 对齐基线与范围

### 已确认的 PoC 实现基线（对齐的"实现侧"事实来源）
- **共享契约包** `packages/clinical-contracts/src/index.mjs`（`@zhenhu/clinical-contracts` v0.1.0）：病例状态机含 `knowledge_changed` 阻断态、`confirmed/rejected/closed/cancelled` 全转移、`CASE_BLOCKING_STATES`；知识版本状态机含 `superseded/archived/review_rejected`。`contracts:test` 7/7。
- **workflow.mjs**：实现 `cancel()`/`close()`/`reconcile()`(reset+runAnalysis)/`onKnowledgeUnavailable()`(知识过期→knowledge_changed)/`supplementTask()`(§3.4 护士补充)；`reviewRisk()` 全部处理完自动→confirmed/rejected；`citation()` 含 `coordinates`+`retrievedAt`。
- **knowledge.mjs / server.mjs**：知识反向阻断钩子；新增端点 `/cancel /close /reconcile /tasks/:id/supplement /knowledge/audit /demo/reset`；resetRuntime 健壮性修复。
- **前端**：工作台同步全状态标签与交互（close/reconcile/supplement 对话框）。
- **测试**：`poc:test` 39/39、`contracts:test` 7/7、新增端点 API 冒烟 12/12。

### 对齐范围
- 正向：`poc/docs/architecture/{01,02,03}.md`、`poc/docs/testing/{04,05}.md`、`poc/docs/CONTEXT.md`。
- 反向：需求规格 v0.2、证据基线 v0.1。

## 2. 差异矩阵（需求条款 ↔ 实现 ↔ 文档 ↔ 动作）

| 需求条款 | PoC 实现 | PoC 文档现状 | 差异类型 | 动作 |
| --- | --- | --- | --- | --- |
| §3.4 病例状态机含 `knowledge_changed` 阻断态 | 已实现（契约+workflow） | 03-状态机.md mermaid 图缺该态、缺 reconcile/onKnowledgeUnavailable；CONTEXT.md 未提 | 文档滞后 | 修 03/CONTEXT |
| §3.4 `confirmed/rejected→task_draft→simulated_published→closed`、非终态→`cancelled` | 已实现 | 03 转移表 `review_pending→task_draft` 跳过 confirmed/rejected 中间态；缺 close/cancel 动作行 | 文档滞后 | 修 03 转移表 |
| §3.4 护士/个案管理师补充任务执行信息 | `supplementTask` 已实现（task_draft/simulated_published 均可） | 02-接口契约.md 缺 `/tasks/:id/supplement` 端点；04-e2e 缺用例 | 文档滞后 | 修 02/04 |
| §4.3 引用含坐标+检索时间 | `citation()` 含 `coordinates`+`retrievedAt` | 01-数据模型.md 的 KnowledgeCitation 字段为 location/excerpt，未列 coordinates/retrievedAt | 命名不一致 | 修 01 字段定义 |
| §4.4 知识版本 `superseded/archived/review_rejected` | 已实现（契约终态） | 03 知识生命周期图只画 published→expired/withdrawn；CONTEXT 同；02 transition 端点只写"发布/过期/撤回" | 文档滞后 | 修 03/CONTEXT/02 |
| §4.4 反向阻断→`knowledge_changed` | `onKnowledgeUnavailable` 已实现 | 03/CONTEXT/04 均未描述阻断与恢复链路 | 文档滞后 | 修 03/CONTEXT/04 |
| §6 接口契约 | cancel/close/reconcile/supplement/audit/demo-reset 已暴露 | 02-接口契约.md 缺 6 个端点；缺 KNOWLEDGE_CHANGED/TASK_NOT_FOUND/RISK_NOT_FOUND 错误码 | 文档滞后 | 修 02 |
| §8.3 验收 8/9（版本撤回/来源失效） | V-27/V-28 已验证 | 04-e2e 未补对应 E2E 用例 | 文档滞后 | 修 04 |
| §0 表（第 21 行）/§8.5（第 313 行）/证据§3.1（第 57 行）"27/27" | 实际 39/39 | 需求与证据仍写 27/27 | 需求侧事实滞后 | 反向-A 类：直接改正文 |
| §0.2 演示剧本 | PoC 已实现 close/reconcile/supplement | 演示剧本 4 步未含新路径 | 需求侧事实滞后 | 反向-A 类：补演示路径 |
| §10.18 关闭标准待确认 | PoC 已验证 closed/cancelled 状态转移 | 需求列为待确认，未注 PoC 已验证 | 需求侧事实滞后 | 反向-A 类：标注 |
| §3.4 主体状态序列表述 | 实现含 knowledge_changed | 需求§3.4 主体段落（第 127 行）状态序列未列 knowledge_changed，仅§4.4 末段（第 167 行）提及 | 需求内部不一致 | 反向-B 类：批注 |
| §3.4 护士补充措辞 | supplementTask 覆盖 task_draft 与 simulated_published | 需求第 127 行"医生模拟确认后的任务草稿"含糊 | 需求表述含糊 | 反向-B 类：批注 |
| §4.3 引用字段命名 | 实现用 coordinates/retrievedAt | 需求用"页码/章节/表格坐标""检索时间"，01 用 location/excerpt | 命名不统一 | 反向-B 类：批注 |
| §4.4 知识生命周期 | 实现拆分为入库任务状态机(queued/parsing)与文档状态机(review_pending 起) | 需求第 160 行把 uploaded/parsing 混入文档生命周期 | 需求表述含糊 | 反向-B 类：批注 |
| §4.4 恢复路径 | `reconcile`(reset+runAnalysis) | 需求第 167 行只说"直至重新检索和人工复核完成"，未定义恢复动作 | 需求含糊 | 反向-B 类：批注 |

## 3. PoC 文档修订清单（正向）

### 3.1 `poc/docs/architecture/03-状态机.md`（最严重滞后）
- 病例 mermaid 图补 `knowledge_changed` 节点及其 `→review_pending`(reconcile)/`→cancelled` 转移；补 `confirmed/rejected/simulated_published→cancelled`。
- 转移规则表补 5 行：`close`(simulated_published→closed)、`cancel`(非终态→cancelled)、`reconcile`(knowledge_changed→review_pending)、`onKnowledgeUnavailable`(review_pending/task_draft→knowledge_changed)、`supplementTask`(不变,记审计)。
- 知识文档生命周期 mermaid 补 `superseded/archived/review_rejected` 终态与 `published→superseded`。
- 不变量补第 6 条：`knowledge_changed` 期间禁止 publish/createTaskDraft。

### 3.2 `poc/docs/architecture/02-接口契约.md`
- 端点表补 6 个：`POST /cases/:caseId/cancel`、`/close`、`/reconcile`、`POST /cases/:caseId/tasks/:taskId/supplement`、`GET /knowledge/audit`、`POST /demo/reset`。
- 错误码表补：`KNOWLEDGE_CHANGED`(409)、`TASK_NOT_FOUND`(404)、`RISK_NOT_FOUND`(404)。
- `transition` 端点描述补 superseded/archived/review_rejected 转移及"过期/撤回/被替代时触发反向阻断"副作用。

### 3.3 `poc/docs/architecture/01-数据模型.md`
- `KnowledgeCitation` 关键字段补 `coordinates`、`retrievedAt`（对齐§4.3）。
- `KnowledgeDocument.status` 补完整枚举说明（含 superseded/archived/review_rejected）。
- `TaskDraft.tasks[].status` 补 `simulated_supplemented`；补 `executionResult` 字段。

### 3.4 `poc/docs/testing/04-e2e-cases.md`
- 补 E2E-11~E2E-15：knowledge_changed 阻断+reconcile 恢复、cancel/close 闭环、护士 supplementTask 跨角色拒绝、知识 superseded 阻断、审计完整性含新事件。

### 3.5 `poc/docs/CONTEXT.md`
- 已验证证据 `26/26`→`39/39`（注：原文写 26/26，实际应为 39/39）。
- "知识生命周期"行补 superseded/archived/review_rejected。
- "当前可运行能力"补第 8 条：knowledge_changed 阻断+reconcile 恢复+close/cancel+护士 supplementTask。

### 3.6 `poc/docs/testing/05-poc-validation-results.md`
- 已含 V-25~V-32（上轮已对齐），仅补一句指向 04-e2e 新用例的映射。

## 4. 需求侧反向标注清单

### A 类：事实性滞后 → 直接修订需求文档正文（无争议，仅更新已验证事实）
1. 需求§0 表（第 21 行）+ §8.5（第 313 行）+ 证据§3.1（第 57 行）：`27/27` → `39/39`。
2. 需求§0.2 演示剧本：补 close/reconcile/supplement 演示路径（PoC 已实现并验证）。
3. 需求§10.18：标注"PoC 已验证 closed/cancelled 状态转移；真实任务关闭的业务标准仍待确认"。

### B 类：设计性含糊/待确认 → 仅加 `【PoC对齐反馈】` 批注，不擅自改写需求意图
1. 需求§3.4 主体状态序列（第 127 行）未列 knowledge_changed（与§4.4 末段内部不一致）→ 批注提示统一。
2. 需求§3.4 护士补充措辞"医生模拟确认后的任务草稿"含糊 → 批注明确覆盖 task_draft 与 simulated_published 两状态。
3. 需求§4.3 引用字段命名不统一（coordinates/retrievedAt vs 页码/章节/坐标 vs location/excerpt）→ 批注建议对齐。
4. 需求§4.4 把 uploaded/parsing 混入文档生命周期 → 批注建议拆为入库任务状态机与文档状态机。
5. 需求§4.4 未定义恢复动作 → 批注建议补 reconcile 动作与 knowledge_changed→review_pending 转移。

## 5. 执行顺序与验收

1. 本报告作为评审基线（已完成）。
2. 正向修订 PoC 文档（按依赖）：03 → 02 → 01 → 04 → CONTEXT → 05。
3. 反向处理需求文档：A 类直接改正文；B 类加 `【PoC对齐反馈】` 批注。
4. 收尾重跑 `npm run poc:test`(39/39) 与 `npm run contracts:test`(7/7)，确认文档修订未误改代码契约。
5. 验收标准：PoC 文档状态枚举与转移表与契约包一致；需求文档测试数字与实际一致；批注可追溯至本报告。

## 6. 边界声明

本轮仅做文档对齐与反馈，不改代码逻辑、不替代医院决策、不构成临床有效性或生产安全结论。B 类批注均留待需求负责人决策，不越权改写需求意图。

## 7. 2026-07-15 后续增强（P0+P1 调研 → 需求修订 → PoC 实现）

### 7.1 需求侧增强

基于 6 个参考开源项目的调研，通过产品经理许清楚独立审查，完成：

| 批次 | 条数 | 内容 | 需求文档受影响章节 |
|---|---|---|---|
| P0 | 6 | 四子任务/出院去向严重度/escalate/非文本分块/后处理管道/Agent 可溯源 | §3.1 §3.4 §4.2 §5 §5.1 |
| P1 | 5 | PlanDefinition/CarePlan 双模式/版本回退/查询审计/工作流检查点 | §4.4 §6.1 §6.2 §7 |
| 决策 | 3 | 患者角色占位/escalate 可选配置/字段级权限声明 | §2 |

5 条 B 类【PoC对齐反馈】批注已全部融入需求正文并移除，需求文档零批注残留。

### 7.2 PoC 实现侧同步

将 P0-1/P0-2/P0-3/P0-6 四条可 PoC 验证的增强落地为代码和文档：

| P0 项 | PoC 实现 | 测试 |
|---|---|---|
| 四子任务 | `risk-dose-01` 新增第 4 风险项（dose_discrepancy）；data_conflict 场景 5 项风险 | TC-04 |
| 出院去向严重度 | `runAnalysis` 中 dischargeTo="居家" 时 medium→high 升级 | TC-03 |
| escalate 升级动作 | `reviewRisk` 新增 escalate 分支；`createTaskDraft` 过滤 escalated；前端升级按钮 + escalated 状态 | TC-01/02 + API 冒烟 |
| Agent 溯源码 | 全部 evidence 对象含 `source_type` 枚举；前端彩色标签 | TC-05 |

### 7.3 验证

| 验证项 | 结果 |
|---|---|
| `npm run poc:test` | **44/44** 通过（39→44，新增 5 个精准用例） |
| `npm run contracts:test` | **7/7** 通过（不变） |
| QA 独立验证 | 全部通过（5 项边界条件 + 5 个新增 TC 深度审查 + 前端语法检查） |
| QA 智能路由判定 | **NoOne**——无 Bug，无需第 2 轮回归 |

PoC 未实现：P0-4/P0-5（分块增强，属正式 RAG 管线）、P0-3 escalate 的 de-escalate 回退、P1-4/P1-7（MedicationRequest 软状态 / On-Behalf-Of，属正式工程范围）。
