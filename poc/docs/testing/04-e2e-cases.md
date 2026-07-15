# PoC 端到端测试用例

测试数据只使用 `CASE-2026-0715-0042` 等预置模拟病例。所有用例应在隔离环境执行，并在运行结束后导出审计事件作为证据。

| ID | 场景 | 前置条件 | 操作 | 预期结果 |
| --- | --- | --- | --- | --- |
| E2E-01 | 正常审核并模拟发布 | 经治医生已登录；3 个风险项待审核 | 依次确认/驳回全部风险项，生成草稿，模拟发布 | 状态依次进入 `task_draft`、`simulated_published`；生成 2 个模拟待办；审计链包含每次决定和发布事件 |
| E2E-02 | 未完成审核禁止生成草稿 | 至少 1 项风险待审核 | 点击生成草稿 | API 返回 `409 CASE_STATE_CONFLICT`；界面提示未完成审核；不出现待办 |
| E2E-03 | 医生编辑后确认 | 一个风险项待审核 | 填写审核说明并保存确认 | 风险项显示已确认和说明；审计包含 `edit_confirm` 与说明摘要 |
| E2E-04 | 权限拒绝 | 使用护士会话 | 调用风险审核接口或尝试审查操作 | 返回 `403 ACCESS_DENIED`；不泄漏风险详情；产生拒绝审计事件 |
| E2E-05 | 输入数据不足 | 模拟病例缺失过敏史字段 | 发起分析 | 状态进入 `failed` 或 `review_pending` 且给出明确缺失项，取决于规则配置；绝不生成可发布草稿 |
| E2E-06 | 检索依赖失败 | 模拟知识服务返回不可用 | 发起分析 | 显示 `DEPENDENCY_UNAVAILABLE` 降级状态；审计记录失败节点；禁止草稿生成 |
| E2E-07 | 过期知识不可引用 | 将知识版本状态改为 `expired` | 发起分析 | 不返回该版本引用；若无替代证据则进入待人工核实或失败状态 |
| E2E-08 | 重复提交幂等 | 使用相同 `idempotency_key` 发布草稿两次 | 连续触发模拟发布 | 仅生成一组任务；第二次返回同一结果或 `409`；审计中可识别重复请求 |
| E2E-09 | 审计完整查询 | 已完成 E2E-01 | 根据 `case_id` 打开审计页 | 能看到输入快照、规则/知识版本、人工决定、草稿和模拟发布事件，且时间顺序正确 |
| E2E-10 | 无真实外部副作用 | 已完成 E2E-01 | 检查模拟待办与网络调用日志 | 仅调用本地模拟队列；不存在真实 HIS/EMR/LIS、短信、患者端或写回请求 |
| E2E-11 | 知识过期反向阻断与 reconcile 恢复 | 病例处于 `task_draft` 且引用了药品说明书 | 知识管理员将该说明书判为 `expired` | 在办病例自动进入 `knowledge_changed`；草稿与任务被清空；`simulate_publish` 返回 `409 KNOWLEDGE_CHANGED`；恢复知识后医生 `reconcile` 回到 `review_pending` |
| E2E-12 | 关闭与取消闭环 | 病例分别处于 `simulated_published` 与 `review_pending` | 经治医生依次调用 `close` 与 `cancel` | `simulated_published`→`closed`；`review_pending`→`cancelled`；终态不可再操作，返回 `409` |
| E2E-13 | 护士补充任务与跨角色拒绝 | 病例已 `simulated_published`，存在指派护士的待办 | 护士补充 `task-01` 执行结果；个案管理师尝试补充同一任务 | 护士补充成功，任务置 `simulated_supplemented` 并写审计；个案管理师返回 `403 ACCESS_DENIED` |
| E2E-14 | 知识被替代阻断 | 病例处于 `review_pending` 且引用了将被替代的文档 | 知识管理员将该文档判为 `superseded` | 病例进入 `knowledge_changed`；引用无关知识的病例不受影响 |
| E2E-15 | 新增事件审计完整性 | 已完成 E2E-11~14 | 按 `case_id` 查询审计 | 审计链包含 `knowledge_changed`、`reconcile`、`case_closed`、`case_cancelled`、`task_supplemented` 事件，时间顺序正确，前后状态可追溯 |
| E2E-16 | escalate 升级后草稿仍可生成 | 病例处于 `review_pending`，4 个风险项待审核 | 确认 3 个风险项，将第 4 个（剂量偏差）escalate 升级 | 病例进入 `confirmed`；生成草稿成功；`basedOnRiskIds` 不包含 escalated 项；escalated 项状态为 `escalated` |
| E2E-17 | 居家患者 medium 风险自动升级为 high | 病例处于 `review_pending`，患者 `dischargeTo="居家"` | 发起分析后查看风险列表 | `risk-renal-01` 和 `risk-dose-01` 的 severity 为 `high`，severityLabel 含"居家升级" |

## 自动化落地

- API/状态机：为每条转移规则和错误码写 Vitest 单元测试。
- 浏览器：使用 Playwright 覆盖 E2E-01、02、03、04、06、08、09、10；E2E-11~15 以 API 冒烟与 `poc/tests/workflow-state-machine.test.mjs`、`knowledge-lifecycle.test.mjs` 覆盖。
- 运行前注入固定时钟与固定 mock 数据，避免时间和随机值影响断言。
- 每次浏览器测试保留截图与 trace 到 `output/playwright/`；禁止提交模拟病例之外的敏感数据。
