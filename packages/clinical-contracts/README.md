# @zhenhu/clinical-contracts

正式项目与 PoC 共同引用的**唯一状态机事实来源**，对照《需求规格说明书 v0.2》：

- 病例状态机：§3.4（含 `knowledge_changed` 阻断态，见 §4.4 末段）
- 知识文档版本状态机：§4.4（`review_rejected` / `superseded` / `archived` 等）
- 入库任务状态机：§4.4（后台异步任务）
- 最小角色访问边界：§2

该包不含部署入口或界面代码，也不得以 PoC 模拟数据作为正式事实来源。任何调用方（包括 `poc/api/workflow.mjs` 与 `services/knowledge-orchestrator`）都应从这里导入状态转移与角色裁决，禁止在各自代码里硬编码状态枚举。

> 原位于 `poc/packages/clinical-contracts`，已按 README 的 `packages/` 约定迁移至本目录（正式项目共享契约的权威位置）。
