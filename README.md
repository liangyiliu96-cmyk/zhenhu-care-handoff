# 臻护 · 全病程数智医护平台

> 面向医护人员的临床决策支持系统 (CDSS),通过受控知识库与多 Agent 工作流,发现出院交接与院后随访中的信息缺漏、冲突和规范风险。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/liangyiliu96-cmyk/zhenhu-care-handoff/actions/workflows/ci.yml/badge.svg)](https://github.com/liangyiliu96-cmyk/zhenhu-care-handoff/actions)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61dafb)](https://react.dev/)

## 项目简介

臻护是全病程数智医护平台:从入院评估、住院协同到出院交接与慢病随访,平台通过 12 节点多 Agent 工作流、16 层 RAG 临床知识引擎与 LLM 辅助推理,辅助医护人员:

- **发现风险**:用药冲突、检验异常、规范偏差、随访缺口
- **生成建议**:可追溯、可审核的临床建议与操作草案
- **协同交接**:多学科团队、护理任务、出院计划全链路留痕
- **持续随访**:慢病患者的院后管理与智能提醒
- **互操作**:HL7 **CDS Hooks** 标准接口(入院确认 / 用药确认 hooks),面向第三方 EMR/HIS 开放

平台遵循**人机协同**原则:AI 提供证据化建议,医生/护士掌握最终决策权。

## ✨ 功能亮点

- **多 Agent 住院协同**:12 节点工作流(入院→查房→检验→出院→随访),规则与 LLM 混合推理
- **16 层临床知识 RAG**:Milvus 向量检索,回答带来源引用,可追溯
- **5 大智能助手**:查房 / 护理 / 用药 / 患教 / 中西医协同(DeepSeek 驱动,规则引擎兜底)
- **国际评估量表**:NRS / NRS2002 / Morse / Padua + CGA(MMSE / ADL / IADL)
- **CDS Hooks 互操作**:标准接口对接第三方 EMR/HIS
- **统一 OIDC 认证 + 全链路审计**:Keycloak 驱动,合规可追溯

## 📸 演示截图

> 运行 `docker compose up -d --build` 后访问 http://127.0.0.1:5173,可将医生工作台 / 患者全貌 / 助手对话截图放入本目录并在此引用。

<!-- 截图占位: 将截图放入 docs/screenshots/ 后取消注释引用
![医生工作台](docs/screenshots/dashboard.png)
![患者全貌](docs/screenshots/patient.png)
![智能助手](docs/screenshots/assistant.png)
-->

## 🚀 快速体验(5 分钟)

```bash
git clone https://github.com/liangyiliu96-cmyk/zhenhu-care-handoff
cd zhenhu-care-handoff
cp .env.example .env
docker compose up -d --build
# 打开 http://127.0.0.1:5173 (开发快捷登录, 或 Keycloak: doctor/doctor123)
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Pydantic v2 |
| 数据库 | MySQL 8.0(三库隔离)· Milvus(向量检索)· Neo4j(证据图谱)· Redis(缓存) |
| LLM | DeepSeek API(deepseek-chat)· 规则引擎兜底 · Ollama 可配回退 |
| 认证 | Keycloak OIDC(生产)· header 演示模式(开发) |
| 前端 | React 18 · Vite · MUI v6 · Zustand · TanStack Query v5 |
| 部署 | Docker Compose(12 容器)· GitHub Actions CI · Alembic 迁移 |

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (React + MUI)                     │
│            nginx 静态托管 + API 代理 (5173)                │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Keycloak OIDC (统一认证, 8080)               │
└──────────────────────┬──────────────────────────────────┘
                       │ JWT
┌──────────────────────▼──────────────────────────────────┐
│   inpatient-ward     workflow-engine    knowledge-orc.   │
│   (住院协同 8001)      (状态机 8100)      (知识编排 8200)   │
│   fhir-adapter       (FHIR 映射 8300)                     │
└──────┬───────────┬───────────┬───────────┬───────────────┘
       │           │           │           │
   ┌───▼───┐  ┌────▼────┐  ┌───▼────┐  ┌───▼────┐
   │ MySQL │  │ Milvus  │  │ Neo4j  │  │ Redis  │
   │ 三库   │  │ 向量检索 │  │ 证据图谱 │  │ 缓存   │
   └───────┘  └─────────┘  └────────┘  └────────┘
```

### 服务拆分

| 服务 | 端口 | 职责 | 测试 |
| --- | --- | --- | --- |
| inpatient-ward | 8001 | 住院协同 12 节点 Agent、14+ 病种模板、评估量表、助手 | 374 |
| workflow-engine | 8100 | 病例状态机、Agent 编排、审核流、审计 | 90 |
| knowledge-orchestrator | 8200 | 知识导入、混合检索、反向阻断、审计 | 49 |
| fhir-adapter | 8300 | FHIR 数据映射、Patient Compartment、Consent | 42 |
| clinical-contracts | — | 共享临床契约(状态机/AgentLoop/断路器) | 7 |

## 项目结构

```
├── docker-compose.yml          # 全栈编排 (12 容器)
├── .github/                    # CI 工作流 + Issue/PR 模板
├── deploy/
│   ├── keycloak/               # OIDC realm 配置
│   └── mysql/init/             # MySQL 三库初始化
├── packages/clinical-contracts-py/  # 共享临床契约 (Pydantic v2)
├── apps/frontend/              # 前端 (React 18 + MUI)
├── services/
│   ├── inpatient-ward/         # 住院协同 (核心业务)
│   ├── workflow-engine/        # 病例状态机
│   ├── knowledge-orchestrator/ # 知识编排
│   └── fhir-adapter/           # FHIR 适配
├── CONTRIBUTING.md             # 贡献指南
├── SECURITY.md                 # 安全与漏洞报告
└── scripts/                    # 辅助脚本
```

## Docker 一键部署

```bash
# 1. 准备环境变量 (可选, 有默认值)
cp .env.example .env
# 生产务必修改: MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD / DEEPSEEK_API_KEY / KEYCLOAK_ADMIN_PASSWORD

# 2. 构建并启动全部服务
docker compose up -d --build

# 3. 访问
#   前端:      http://127.0.0.1:5173
#   API 文档:  http://127.0.0.1:8001/docs
#   Keycloak:  http://127.0.0.1:8080

# 可选: 监控栈 (Prometheus + Alertmanager)
docker compose --profile monitoring up -d

# 停止 / 清理 (加 -v 删除数据卷)
docker compose down [-v]
```

| 服务 | 宿主机端口 | 说明 |
| --- | --- | --- |
| frontend | 5173 | nginx 静态托管 + API 代理 |
| inpatient-ward | 8001 | 住院协同(业务核心) |
| workflow-engine | 8100 | 病例状态机 |
| knowledge-orchestrator | 8200 | 知识编排 |
| fhir-adapter | 8300 | FHIR 映射 |
| keycloak | 8080 | OIDC 认证 |
| mysql / redis / milvus / neo4j / etcd / minio | 3307 / 6379 / 19530 / 7474·7687 / — / — | 数据层 |

> 注:宿主机 MySQL 端口默认 3307(避免与本机 MySQL 冲突,可用 `MYSQL_HOST_PORT` 调整)。

### 认证模式

- **演示(默认)**:`.env` 设 `APP_ENV=dev` + `AUTH_MODE=header`,开发快捷登录
- **生产**:`.env` 设 `APP_ENV=production` + `AUTH_MODE=oidc`,Keycloak 登录(演示账号 `doctor/doctor123`、`nurse/nurse123`、`admin/admin123`)

### 生产部署安全清单

上线前必须完成以下事项(默认值均为本地演示用途):

- [ ] **修改全部默认密码**:`MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` / `NEO4J_PASSWORD` / `KEYCLOAK_ADMIN_PASSWORD`(demo 账号 `doctor123` 等)
- [ ] **启用 OIDC 认证**:`APP_ENV=production` + `AUTH_MODE=oidc`(生产强制,header 模式被拒绝)
- [ ] **配置 DeepSeek Key**:`.env` 的 `DEEPSEEK_API_KEY`(未配置则助手回退规则引擎)
- [ ] **配置 TLS**:前置反向代理(nginx/caddy)终止 HTTPS,并设置 `ALLOWED_HOSTS`
- [ ] **移除演示账号**:生产 realm 仅保留真实医护账号(删除 doctor/nurse/admin demo 用户)
- [ ] **数据备份**:MySQL 定时备份 + 恢复演练(三库 zhenhu_workflow / knowledge / fhir)

### LLM 配置

```bash
# .env 中配置 (未配置时自动回退规则引擎, 不影响核心流程)
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat
```

## 测试

- **后端**:4 服务全量 555 项(workflow 90 / knowledge 49 / fhir 42 / inpatient 374,含 MySQL 集成测试)
- **前端**:179 项(vitest,58 个测试文件)
- **契约**:7 项(clinical-contracts)
- **CI**:GitHub Actions 3 job 全绿(backend / frontend / lint),main 分支受保护

## 路线图

- [x] PoC 验证与临床契约移植
- [x] 四大后端服务 + 前端联调
- [x] Docker 全栈部署(Milvus/Neo4j/Keycloak 落地)
- [x] LLM 接入(DeepSeek)+ 16 层 RAG 知识引擎
- [x] Phase 0:CI/CD、ruff、依赖锁定、模型预缓存
- [x] Phase 1a:Alembic 迁移、审计补全
- [x] Phase 1b:Keycloak OIDC 统一鉴权
- [ ] Phase 2:开源 HIS 对接(FHIR)、知识入口统一、可观测性
- [ ] Phase 3:K8s 部署、多租户、等保合规

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全问题见 [SECURITY.md](SECURITY.md)。

## License

[MIT](LICENSE)
