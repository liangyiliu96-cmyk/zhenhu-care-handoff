# PoC 验证结果

验证日期：2026-07-15（本轮更新：状态机对齐需求 §3.4/§4.4、知识反向阻断、护士任务补充、前端同步、运行时重置修复）

## 已执行验证

| 编号 | 验证 | 结果 | 证据 |
| --- | --- | --- | --- |
| V-01 | 工作流、知识与解析模块单元测试 | 通过：44/44 | `npm run poc:test`（含新增 `workflow-state-machine.test.mjs` 14 例、`knowledge-lifecycle.test.mjs` 3 例） |
| V-02 | 护士审核权限拒绝 | 通过：`403 ACCESS_DENIED` | API 冒烟请求 |
| V-03 | 未完成审核禁止草稿 | 通过：`409 CASE_STATE_CONFLICT` | API 冒烟请求 |
| V-04 | 医生审核、草稿、模拟发布 | 通过：最终状态 `simulated_published` | API 冒烟请求 |
| V-05 | 模拟待办与审计下游可见性 | 通过：2 个任务、10 条审计事件 | API 冒烟请求与工作台刷新 |
| V-06 | 模拟检索依赖失败 | 通过：进入 `failed`，不生成风险或草稿 | 工作流单元测试 |
| V-07 | 浏览器工作台 | 通过：服务端状态回显、控制台 0 错误/0 警告 | Playwright 截图 `output/playwright/poc-api-workflow-final.png` |
| V-08 | 知识版本过期 | 通过：进入 `failed`，不返回风险项或草稿 | 工作流单元测试 |
| V-09 | 输入来源冲突 | 通过：两个来源并列为待审核项，不自动合并 | 工作流单元测试 |
| V-10 | 重复模拟发布 | 通过：第二次发布返回状态冲突 | 工作流单元测试 |
| V-11 | 服务健康检查 | 通过：`GET /healthz` 返回 `ok` | API 冒烟请求 |
| V-12 | 场景化 API 冒烟 | 通过：来源冲突产生 4 项待审核项；知识过期返回 `422` | API 冒烟请求 |
| V-13 | 护理角色最小视图 | 通过：发布前不返回风险、审计或任务草稿 | 工作流单元测试 |
| V-14 | 场景与角色工作台 | 通过：来源冲突显示第 4 项风险；知识过期明确降级；护理角色只读 | Playwright 浏览器验证 |
| V-15 | 受控知识检索基线 | 通过：3 份已发布文档可见；词法检索返回可追溯分块引用 | API 冒烟与 Playwright 浏览器验证 |
| V-16 | 本地向量检索融合 | 通过：中文连续查询返回稳定引用、余弦与词法分数、检索策略版本 | 知识模块单元测试 |
| V-17 | 多语言嵌入模型 | 通过：384 维语义向量、正确引用、模型与策略可见、浏览器零错误 | `npm run poc:verify-embedding` 与 Playwright |
| V-18 | 受控文本入库生命周期 | 通过：知识管理员导入 `.txt/.md` 后为 `review_pending` 且检索为 0；发布后返回新分块；过期或撤回后排除 | 单元测试、API 冒烟与 Playwright 截图 `output/playwright/poc-knowledge-ingestion-lifecycle.png` |
| V-19 | 知识管理员最小权限视图 | 通过：不请求病例概览，不显示病例标识或场景栏；可导入、发布、过期、撤回知识资产 | Playwright 浏览器验证，控制台 0 错误/0 警告 |
| V-20 | 受控 PDF/DOCX 解析 | 通过：PDF 真实夹具提取正文；DOCX 最小 Open XML 夹具提取正文；MIME、签名错误明确拒绝 | `poc/tests/document-parser.test.mjs` |
| V-21 | 异步入库任务与可重试失败恢复 | 通过：导入先返回 `queued`，完成后才创建 `review_pending`；失败任务可在修正后重试恢复 | `poc/tests/knowledge.test.mjs` 与 API 冒烟 |
| V-22 | 知识运行时本地恢复与预置样例重置 | 通过：重建注册表后保留导入文档与入库任务；恢复预置样例后清空运行时状态文件 | `poc/tests/knowledge.test.mjs` |
| V-23 | 知识管理员页面恢复预置样例演示 | 通过：真实浏览器导入 `.md` 样例后显示 1 条入库任务与 1 份待审核文档；恢复后回到 3 份预置知识、0 条入库任务 | Playwright 截图 `output/playwright/poc-knowledge-runtime-before-reset-2026-07-15.png`、`output/playwright/poc-knowledge-runtime-after-reset-2026-07-15.png`，控制台 0 错误/0 警告 |
| V-24 | 知识恢复 API 冒烟 | 通过：`POST /api/v1/knowledge/runtime/reset` 返回 `documentCount=3`、`importJobCount=0`；恢复后 `GET /api/v1/knowledge/documents` 返回 3 份预置知识 | API 冒烟请求 |
| V-25 | 共享临床契约包 | 通过：7/7；病例状态机（§3.4）与知识版本状态机（§4.4）转移表、阻断态、角色边界均有契约断言 | `npm run contracts:test`（`packages/clinical-contracts`，从 poc 迁移并扩展） |
| V-26 | 病例状态机完整转移（§3.4） | 通过：`confirmed/rejected → task_draft`、`simulated_published → closed`、非终态 `→ cancelled`、`knowledge_changed → review_pending`（经 reconcile）均符合契约 | `poc/tests/workflow-state-machine.test.mjs` |
| V-27 | 知识反向阻断在办病例（§4.4） | 通过：已发布知识过期/撤回/被替代时，引用它的 `review_pending`/`task_draft` 病例进入 `knowledge_changed` 且发布被阻断（`409 KNOWLEDGE_CHANGED`）；引用无关知识的病例不受影响 | `poc/tests/workflow-state-machine.test.mjs` 与 API 冒烟 |
| V-28 | 知识版本终态与审核驳回（§4.4） | 通过：`superseded`/`archived` 为终止态不可再转移；`review_rejected` 后不可再 `published`；服务端钩子在知识不可用时触发阻断 | `poc/tests/knowledge-lifecycle.test.mjs` |
| V-29 | 引用坐标与时间戳（§4.3） | 通过：`citation()` 包含 `coordinates`（分块定位）与 `retrievedAt`（检索时间），构成不可变审计证据 | `poc/api/knowledge.mjs` 与知识检索单元测试 |
| V-30 | 护士/个案管理师任务执行补充（§3.4） | 通过：指派角色可 `supplementTask` 将任务标记 `simulated_supplemented` 并记录执行结果；跨角色补充返回 `403 ACCESS_DENIED` | `poc/tests/workflow-state-machine.test.mjs` 与 API 冒烟 |
| V-31 | 前端状态机同步 | 通过：工作台覆盖 `confirmed/rejected/knowledge_changed/closed/cancelled` 全状态标签与分支；主操作按钮联动 `生成草稿/模拟发布/关闭/重新核实`；护士任务补充对话框可用 | `poc/web/app.js`、`index.html` 语法检查通过；API 冒烟 12/12 |
| V-32 | 运行时重置健壮性 | 通过：`resetRuntime` 在受控环境拦截文件删除时回退为写回预置状态，不再返回 `INTERNAL_ERROR` | API 冒烟：`transition → resetRuntime` 链路 |
| V-33 | P0 需求增强（四子任务/出院去向严重度/审核升级/Agent溯源码） | 通过：dose_discrepancy 风险项可 escalate 升级；dischargeTo="居家" 时 medium→high；data_conflict 场景 5 风险项；所有 evidence 含 source_type；escalated 不阻止草稿生成且不计入 confirmed/rejected 统计 | `poc/tests/workflow-state-machine.test.mjs` 新增 5 例 |

## E2E 用例映射

V-26~V-28、V-30、V-32、V-33 的 API 冒烟对应 `poc/docs/testing/04-e2e-cases.md` 新增的 E2E-11~E2E-17（knowledge_changed 阻断+reconcile、cancel/close 闭环、护士 supplementTask 跨角色拒绝、知识 superseded 阻断、审计完整性、escalate 升级、居家严重度升级）。E2E-11~17 由 `poc/tests/workflow-state-machine.test.mjs`、`knowledge-lifecycle.test.mjs` 及 API 冒烟覆盖；浏览器 Playwright 覆盖范围维持 E2E-01~10。

## 验证结论

本轮已验证 PoC 的服务端主链路：模拟输入快照 -> 确定性规则与模拟知识引用 -> 医生审核 -> 任务草稿 -> 模拟发布 -> 模拟待办与审计；以及知识管理员 `.txt/.md/.pdf/.docx` 导入 -> 异步队列 -> 自动稳定分块 -> 待审核 -> 发布/过期/撤回 -> 检索索引同步。知识子系统现已具备本地运行时恢复与一键恢复预置样例能力，并已通过真实浏览器演示和 API 冒烟取证。工作台不再以浏览器数组作为业务事实来源。

本轮新增：将病例状态机从简化版对齐到需求 §3.4/§4.4 完整契约（`confirmed/rejected/knowledge_changed/closed/cancelled` 全转移），共享临床契约包迁移至根 `packages/clinical-contracts` 并通过 7/7 契约测试；实现知识过期/撤回/被替代时对在办病例的反向阻断（§4.4）与 `reconcile` 重新核实恢复；补全引用坐标与检索时间戳（§4.3）及护士/个案管理师任务执行补充（§3.4）；前端工作台同步全部新状态与交互（含关闭、重新核实、任务补充对话框）。修复 `resetRuntime` 在受控环境拦截文件删除时返回 `INTERNAL_ERROR` 的问题（回退写回预置状态）。

本轮增量：落地 4 条 P0 需求增强——新增剂量偏差（dose_discrepancy）第 4 个风险项；出院去向感知严重度（dischargeTo="居家" 时 medium 自动升级为 high）；审核升级动作（escalate，已升级项不阻止草稿生成且不计入 confirmed/rejected 统计）；所有 evidence 增加 source_type 溯源标签。PoC 单元测试从 39/39 扩展到 44/44，契约测试 7/7，新增端点 API 冒烟全绿。

## 未覆盖边界

- 知识导入当前覆盖受控 `.txt/.md/.pdf/.docx` 和进程内索引；尚未实现病毒扫描、对象存储、持久化异步任务队列、向量数据库、审核双人复核、PDF OCR、加密文件解密或真实知识治理。
- Agent 编排当前由确定性工作流模拟，不调用 LLM、外部网络或真实工具。
- 身份和权限是 PoC 请求头模拟，未接入真实身份提供方、患者关系、资源级授权或会话有效期。
- 病例工作流、病例审计和模拟待办仍为进程内存状态；知识文档、知识审计和入库任务仅实现本地文件恢复，尚未实现生产级持久化、并发控制、备份恢复或防篡改审计。
- 未接入 HIS、EMR、LIS、FHIR 服务端、真实通知或任何生产写回接口。

这些未覆盖项意味着当前结果只证明技术流程和接口边界可行，不能作为临床有效性、生产安全性或医院试点准入结论。
