# 项目长期记忆

## 仓库结构约定
- **双轨隔离仓库**: `poc/`(冻结,44/44测试) + 正式工程(`apps/ services/ packages/ tests/`)。
- **隔离红线**: 正式代码不得 `import` 任何 `poc/` 实现。唯一允许的跨目录引用: `from zhenhu.contracts import ...`(来自 `packages/clinical-contracts-py/`)。
- **共享临床契约**: JS 版 `packages/clinical-contracts/src/index.mjs`(v0.1.0,POC用) + Python 版 `packages/clinical-contracts-py/src/zhenhu/contracts/`(v0.2.0,正式工程用,Pydantic v2+Enum)。
- **namespace package**: 正式工程使用 `zhenhu.*` 命名空间(zhenhu.contracts / zhenhu.workflow), 各包通过 pyproject.toml 声明依赖。

## 正式工程技术栈(架构 v0.2 冻结)
- **后端**: FastAPI (Python 3.12+) + SQLAlchemy 2.0 async + Pydantic v2 + Celery + Redis
- **数据库**: MySQL 8.0(业务数据,三库隔离 zhenhu_workflow/zhenhu_knowledge/zhenhu_fhir) + Milvus Lite(向量检索,HNSW索引)
- **前端**: Vite + React 18 + MUI v6 + Tailwind + Zustand + TanStack Query v5 + React Hook Form + Zod
- **部署**: Docker Compose(阶段0,5容器: MySQL+Milvus+Redis+FastAPI+Celery+React) → K8s(阶段2)
- **LLM管线**: LangChain + sentence-transformers 原生加载(不用子进程)

## 服务拆分(4服务+1包)
| 服务 | 目录 | 职责 | 状态 |
|---|---|---|---|
| workflow-engine | `services/workflow-engine/` | 病例状态机/Agent编排/审核流 | ✅ 81测试,10端点 |
| knowledge-orchestrator | `services/knowledge-orchestrator/` | 知识导入/混合检索/后处理/反向阻断 | ✅ 47测试,7端点 |
| fhir-adapter | `services/fhir-adapter/` | 医院数据映射/Patient Compartment/Consent | ❌ 待建 |
| api-gateway | `services/api-gateway/` | 前端网关/路由/鉴权 | ❌ 待建 |
| clinical-contracts | `packages/clinical-contracts-py/` | Pydantic状态机/角色权限 | ✅ 已移植 |

## 测试命令
- `npm run poc:test` → `node --test poc/tests/*.test.mjs`（当前 44/44）
- `npm run contracts:test` → `node --test tests/contracts/*.test.mjs`（当前 7/7）
- `cd services/workflow-engine && python -m pytest -v`（当前 81/81）
- `cd services/knowledge-orchestrator && python -m pytest -v`（当前 47/47）
- 全部: 128 项测试全绿（正式工程）+ 51 项（PoC + contracts）= 179 项

## 关键架构文档
- `docs/requirements/AI出院交接与慢病随访协同平台_需求规格说明书_v0.2.md` — 需求基线(16条增强,冻结)
- `docs/architecture/00-系统架构总览.md` — v0.2(FastAPI+MySQL/Milvus+前端MUI)
- `docs/architecture/01-数据模型与存储方案.md` — 4服务17表+ER图+MySQL三库隔离
- `docs/architecture/03-接口契约与API设计.md` — 3服务23端点+11错误码+UnifiedResponse
- `docs/requirements/需求与PoC对齐反馈报告_v0.1.md` — 双向对齐追溯基线
- `docs/requirements/需求增强建议_来自参考项目_v0.1.md` — 6参考项目18条建议

## PoC 运行注意(已冻结,仅维护)
- 首次语义检索会下载 `Xenova/paraphrase-multilingual-MiniLM-L12-v2`模型。
- `demo/reset` 只重置病例工作流,不重置知识库。
- `resetRuntime` 的 `rmSync` 在沙箱内被拦截,已加 try/catch 回退 `persistState()`。
- PoC 新增能力: escalate升级/dose_discrepancy第4风险项/dischargeTo严重度调整/source_type溯源标签。

## Git 基线(按时间)
```
cc41fed  workflow-engine 补全7端点+hook (81/81)
48f262b  knowledge-orchestrator 知识编排服务 (47/47)
236ae96  gitignore 清理
1fe19fb  01数据模型 + 03接口契约
fed28fa  clinical-contracts Python移植 + workflow-engine骨架 (58/58)
e63a5b9  架构总览 v0.2 — FastAPI+MySQL/Milvus+前端完整方案
75d4b40  架构总览 v0.1 — Node.js 初始版
c597fc4  项目初始化
```

## 文档编号体系
- `docs/requirements/`: 需求层(需求规格/证据基线/对齐报告/增强建议)
- `docs/architecture/`: 架构层(00总览/01数据模型/03接口契约/04-07待补)
- `poc/docs/architecture/`: PoC架构(00-04,已冻结)
- `poc/docs/testing/`: PoC测试(04-e2e/05-验证结果)
