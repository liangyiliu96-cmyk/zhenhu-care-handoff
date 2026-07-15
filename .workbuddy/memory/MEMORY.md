# 项目长期记忆

## 仓库结构约定
- **双轨隔离仓库**: `poc/`(可运行 PoC) + 正式工程骨架(`apps/ services/ packages/ tests/`)。
- **隔离红线**: 正式代码不得 `import` 任何 `poc/` 实现；仅可迁移已验证的契约/状态机/测试场景到 `packages/`。
- **共享临床契约**: `packages/clinical-contracts/src/index.mjs`（`@zhenhu/clinical-contracts` v0.1.0）——病例状态机(§3.4)与知识版本状态机(§4.4)的唯一事实来源。workflow.mjs 通过 `assertCaseTransition` 依赖它。

## 测试命令
- `npm run poc:test` → `node --test poc/tests/*.test.mjs`（当前 39/39）
- `npm run contracts:test` → `node --test tests/contracts/*.test.mjs`（当前 7/7）
- `npm run poc:serve` → `node poc/api/server.mjs`（默认端口 4173）

## PoC 运行注意
- 首次语义检索会下载 `Xenova/paraphrase-multilingual-MiniLM-L12-v2`（384 维）模型；核心工作流端点不需要模型，可离线验证。
- `demo/reset` 只重置病例工作流，**不重置知识库**；要恢复知识预置样例用 `POST /knowledge/runtime/reset`（需 knowledge_admin 角色）。
- 已过期/撤回/被替代的知识为终态，不可恢复为 published；需通过 resetRuntime 回到预置样例。
- `resetRuntime` 的 `rmSync` 在 WorkBuddy 沙箱内会被删除守卫拦截，已加 try/catch 回退 `persistState()`。

## 状态机要点（§3.4 / §4.4）
- 病例: draft→analysing→review_pending→confirmed|rejected→task_draft→simulated_published→closed；任意非终态→failed/cancelled；knowledge_changed 为阻断态(经 reconcile→review_pending 恢复)。
- 知识反向阻断: 已发布知识 expired/withdrawn/superseded 时，引用它的 review_pending/task_draft 病例→knowledge_changed 并阻断发布。
- 护士/个案管理师可 `supplementTask` 补充指派给自己的任务执行信息（§3.4）。

## 需求文档
- `docs/requirements/` 下需求规格 v0.2 + 证据基线 v0.1（四级证据 A/B/C/D）。
- PoC 仅验证技术流程，不证明临床有效性。
