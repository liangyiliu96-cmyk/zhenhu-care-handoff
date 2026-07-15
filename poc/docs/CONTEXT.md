# PoC 延续上下文

最后更新：2026-07-15

## 目录边界

- `poc/` 是独立的可执行验证区，允许放置 PoC 依赖、模拟数据、测试、页面和模型缓存。
- 根目录 `apps/`、`services/`、`packages/`、`tests/` 预留给正式项目，不能直接依赖或混入 `poc/` 实现。
- 正式项目只迁移经过验证的领域契约、状态机、测试场景和交互原则，不迁移 PoC 内存实现。

## 当前可运行能力

1. 模拟病例：确定性风险识别、医生审核、任务草稿、模拟发布、模拟待办和审计。
2. 角色隔离：医生、护理随访、审计员、知识管理员；权限由服务端裁决。
3. 场景降级：输入来源冲突、知识过期、依赖失败均明确失败，不生成任务草稿。
4. 受控知识检索：预置知识仅在 `published` 且有效期内参与检索；支持本地 TF-IDF 与多语言嵌入混合检索，并在模型失败时明确降级。
5. 受控文件入库：知识管理员可导入 `.txt` / `.md` / `.pdf` / `.docx`；服务端校验元数据、日期、扩展名、MIME、5 MiB 大小、签名和源文件哈希，先进入异步队列，解析后自动稳定分块，初始状态固定为 `review_pending`。
6. 本地恢复能力：知识文档、入库任务和知识审计会写入 `poc/data/runtime/knowledge-state.json`，服务重启后可恢复；知识管理员可一键恢复预置样例。
7. 知识生命周期：`review_pending -> published | withdrawn | review_rejected`，`published -> expired | withdrawn | superseded | archived`；终态不可恢复为 published；发布后可检索，过期/撤回/被替代/归档后立即排除并记录知识审计事件。
8. 知识反向阻断与病例闭环（§3.4/§4.4）：已发布知识过期/撤回/被替代时，引用它的在办病例进入 `knowledge_changed` 阻断态，清空草稿并禁止发布；医生可 `reconcile` 重新检索分析恢复至 `review_pending`，或 `cancel`/`close` 闭环；护士/个案管理师可 `supplementTask` 补充指派任务执行信息。
9. 出院去向感知严重度：居家场景下 medium 风险自动升级为 high。
10. escalate 风险升级：医生可将单项风险标记为"需上级复核/需 MDT 讨论"，已升级项不阻止草稿生成。

## 已验证证据

- `npm run poc:test`：44/44 通过，覆盖真实 PDF 与 DOCX 解析夹具、签名和 MIME 拒绝路径、异步入库任务、失败重试、本地恢复与恢复预置样例，以及病例状态机全转移、知识反向阻断、reconcile 恢复、护士任务补充、escalate 升级、出院去向严重度（`workflow-state-machine.test.mjs`、`knowledge-lifecycle.test.mjs`）。
- `npm run contracts:test`：7/7 通过；`packages/clinical-contracts` 为病例/知识/入库状态机唯一事实来源。
- `npm run poc:verify-embedding`：通过；模型为 `Xenova/paraphrase-multilingual-MiniLM-L12-v2`，输出维度为 384。
- 浏览器验证：知识管理员导入后检索为 0，发布后检索返回新分块；控制台 0 错误/0 警告。
- 详情见 `poc/docs/testing/05-poc-validation-results.md` 和 `output/playwright/`。

## 运行方式

```powershell
npm run poc:serve
npm run poc:test
npm run poc:verify-embedding
```

默认服务地址：`http://127.0.0.1:4173`。

## 当前限制

- 只使用合成/脱敏模拟数据；不连接 HIS、EMR、LIS、FHIR、真实通知或生产写回。
- 病例工作流、模拟待办和病例审计仍为进程内存数据；仅知识文档、知识审计和入库任务支持本地运行时恢复。
- 已有本地文件恢复和异步入库队列，但尚未实现持久化 worker、对象存储、病毒扫描、PDF OCR、向量数据库、双人审核或真实身份权限。
- 结果只能证明技术流程和接口边界可行，不能作为临床有效性、生产安全性或医院试点准入结论。

## 下一优先级

在保持 PoC 与正式项目隔离的前提下，下一轮建议验证对象存储替代层、持久化任务队列和更完整的检索索引生命周期。持久化、真实身份权限、医院接口和生产级 RAG 应在正式项目架构就绪后分别接入与验收。
