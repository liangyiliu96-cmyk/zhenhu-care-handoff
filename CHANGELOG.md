# Changelog

本项目的所有显著变更均记录于此。

## [0.1.0] - 2026-08-11

首个稳定版发布。

### 新增

- 四大后端服务:inpatient-ward / workflow-engine / knowledge-orchestrator / fhir-adapter
- 前端(React 18 + MUI),nginx 静态托管与 API 代理
- Docker Compose 全栈部署(12 容器:MySQL 三库 / Redis / Milvus / Neo4j / etcd / minio / Keycloak)
- 住院协同 12 节点 Agent 工作流 + 14+ 病种模板 + 4 项国际评估量表
- 16 层 RAG 临床知识引擎(Milvus 向量检索,385 文档)
- 5 大智能助手(查房 / 护理 / 用药 / 患教 / 中西医),DeepSeek LLM + 规则引擎兜底
- Keycloak OIDC 统一认证(4 服务 + 前端 PKCE)
- Alembic 数据库迁移(3 服务,含 legacy 库引导)
- 审计日志(workflow / knowledge / inpatient)
- HL7 CDS Hooks 互操作接口
- GitHub Actions CI(后端 555 / 前端 179 / lint 全绿)+ CodeQL 安全扫描

### 工程化

- Phase 0:CI/CD、ruff lint、依赖锁定、模型预缓存
- Phase 1a:Alembic 迁移、审计补全
- Phase 1b:Keycloak OIDC 统一鉴权
