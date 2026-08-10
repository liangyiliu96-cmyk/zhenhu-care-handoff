# 臻护 · 全病程数智医护平台

> 面向医护人员的临床决策支持系统 (CDSS),通过受控知识库与多 Agent 工作流,发现出院交接与院后随访中的信息缺漏、冲突和规范风险。

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![Python](https://img.shields.io/badge/Python-3.12+-blue)

![FastAPI](https://img.shields.io/badge/FastAPI-0.11+-green)

![React](https://img.shields.io/badge/React-18-blue)

![Tests](https://img.shields.io/badge/Tests-295%20passing-brightgreen)

---

## 项目简介

「臻护」面向医生、护士与随访人员,围绕 **出院交接** 与 **慢病随访** 两大核心场景,提供:

- **多 Agent 临床协同**:住院协同 12 节点 Agent 工作流(入院评估 → 病程监测 → 出院准备 → 出院交接 → 随访计划)
- **受控知识库**:14 种慢病病种模板 + 39 条药物规则,支持规则引擎与 LLM 语义检索双通道
- **临床精度保障**:4 项国际标准入院评估(NRS / NRS2002 / Morse / Padua)+ 3 项老年综合评估(MMSE / ADL / IADL)
- **FHIR 互操作**:医院数据映射、Patient Compartment、患者授权(Consent)管理
- **LLM 容错设计**:LLM 调用异常时自动回退规则引擎,不阻断临床流程

## 技术栈

| 层      | 技术                                                                                        |
| ------ | ----------------------------------------------------------------------------------------- |
| 后端     | Python 3.12+ · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Celery · Redis            |
| 数据库    | MySQL 8.0(业务三库隔离:workflow / knowledge / fhir)· Milvus Standalone(向量检索,HNSW)                 |
| 前端     | Vite · React 18 · MUI v6 · Tailwind · Zustand · TanStack Query v5 · React Hook Form · Zod |
| LLM 管线 | LangChain · sentence-transformers(本地嵌入)· DeepSeek API(可选)                                 |
| 部署     | Docker Compose(MySQL + Milvus + Redis + FastAPI + Celery + React)→ 后续 K8s                 |

## 架构总览

```
┌─────────────┐      ┌──────────────────────────────────────┐
│   React 前端  │      │              API Gateway              │
│   (Vite 5173) │ ───► │      （路由 / 鉴权 / 统一响应）         │
└─────────────┘      └───────────────┬──────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
   │ workflow-engine │    │knowledge-      │    │  fhir-adapter  │
   │  8100 状态机/Agent│    │orchestrator    │    │  8300 FHIR映射  │
   │  编排/审核流      │    │ 8200 知识检索    │    │  Patient/Consent│
   └────────────────┘    └────────────────┘    └────────────────┘
              │
   ┌──────────▼──────────┐
   │   inpatient-ward     │  8001 (宿主机) / 8000 (容器)
   │   12节点Agent + 14病种 │  ← 核心业务服务
   └──────────────────────┘
```

## 项目结构

```
zhenhu-care-handoff/
├── docker-compose.yml           # 全栈编排 (MySQL + Redis + 4 后端 + 前端)
├── deploy/
│   └── mysql/init/              #   MySQL 三库隔离初始化脚本
├── docs/                       # 项目文档
│   ├── requirements/           #   需求规格 v0.2 / 证据基线 / 对齐报告
│   └── architecture/           #   架构设计 00-14 / P0 修复方案
├── packages/
│   ├── clinical-contracts/     #   JS 版临床契约 (PoC 用, v0.1.0)
│   └── clinical-contracts-py/  #   Python 版临床契约 (正式工程用, v0.2.0)
├── apps/
│   └── frontend/               #   前端应用 (React 18 + MUI, 含 Dockerfile + nginx)
├── services/
│   ├── workflow-engine/        #   病例状态机 / Agent 编排 / 审核流
│   ├── knowledge-orchestrator/ #   知识导入 / 混合检索 / 反向阻断
│   ├── fhir-adapter/           #   医院数据映射 / Patient Compartment
│   └── inpatient-ward/         #   住院协同 12 节点 Agent + 14 病种模板
├── tests/                      #   契约测试 (跨服务)
├── scripts/                    #   开发 / 分析脚本
└── poc/                        #   PoC 验证区 (独立, 不参与正式工程)
```

## 快速开始

### 环境要求

- Python ≥ 3.12
- Node.js ≥ 22 (npm ≥ 10)
- 可选:MySQL 8.0、Redis、Docker(生产部署)

### 一键启动

```bash
# 环境变量模板 (可选配置)
cp .env.example .env

# 启动 4 个后端服务 + 健康检查
bash start.sh
# 开发模式跳过 FHIR 同步: SKIP_BRIDGE=true bash start.sh
```

### 手动启动

```bash
# 1. 住院协同服务 (宿主机 8001)
cd services/inpatient-ward
python -m uvicorn zhenhu.inpatient.main:app --host 127.0.0.1 --port 8001

# 2. workflow-engine (8100)
cd services/workflow-engine
python -m uvicorn zhenhu.workflow.main:app --host 127.0.0.1 --port 8100

# 3. knowledge-orchestrator (8200)
cd services/knowledge-orchestrator
python -m uvicorn zhenhu.knowledge.main:app --host 127.0.0.1 --port 8200

# 4. fhir-adapter (8300)
cd services/fhir-adapter
python -m uvicorn zhenhu.fhir.main:app --host 127.0.0.1 --port 8300

# 5. 前端 (5173)
cd apps/frontend
npm install
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>,后端 API 文档见 <http://127.0.0.1:8001/docs>。

## Docker 一键部署

完整全栈编排(MySQL 三库隔离 + Redis + Milvus Standalone 三件套 + 4 后端服务 + 前端 nginx),根目录 `docker-compose.yml`:

```bash
# 1. 准备环境变量 (可选, 有默认值)
cp .env.example .env
# 生产环境务必修改: MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD / DEEPSEEK_API_KEY

# 2. 构建并启动全部服务
docker compose up -d --build

# 3. 访问
#   前端:      http://127.0.0.1:5173  (nginx 代理 API 到 inpatient-ward)
#   API 文档:  http://127.0.0.1:8001/docs

# 可选: 启用监控栈 (Prometheus + Alertmanager)
docker compose --profile monitoring up -d

# 停止 / 清理 (加 -v 删除数据卷)
docker compose down [-v]
```

| 服务                     | 宿主机端口 | 容器端口 | 说明                                |
| ---------------------- | ----- | ---- | --------------------------------- |
| frontend               | 5173  | 80   | nginx 静态托管 + API 代理               |
| inpatient-ward         | 8001  | 8000 | 住院协同(业务核心)                        |
| workflow-engine        | 8100  | 8100 | 病例状态机 / Agent 编排                  |
| knowledge-orchestrator | 8200  | 8200 | 知识检索与编排                           |
| fhir-adapter           | 8300  | 8300 | FHIR 数据映射                         |
| mysql                  | 3306  | 3306 | 三库隔离(workflow / knowledge / fhir) |
| redis                  | 6379  | 6379 | 缓存 / 任务队列                         |
| milvus                 | 19530 | 19530 | 向量数据库(RAG)                        |
| etcd                   | -     | 2379 | Milvus 元数据存储(仅内部)                |
| minio                  | -     | 9000 | Milvus 对象存储(仅内部)                 |



> 说明:向量检索采用 **Milvus Standalone**(etcd + minio + milvus v2.6.1),inpatient-ward 启动时自动初始化 RAG 索引。

### 环境变量

| 变量                    | 默认值                          | 说明                                 |
| --------------------- | ---------------------------- | ---------------------------------- |
| `DEEPSEEK_API_KEY`    | (空)                          | DeepSeek API 密钥;未设置时使用规则引擎         |
| `SKIP_BRIDGE`         | `false`                      | `true` 时跳过 FHIR HTTP 同步,使用 mock 数据 |
| `FHIR_ADAPTER_URL`    | `http://127.0.0.1:8300/fhir` | FHIR 适配器地址                         |
| `INPATIENT_PORT`      | `8001`                       | 住院协同服务端口                           |
| `APP_ENV`             | `dev`                        | 运行环境 `dev` / `production`          |
| `GRAPH_MODE`          | `classic`                    | Agent 编排模式 `classic` / `langgraph` |
| `DOCTOR_AUTO_APPROVE` | `true`                       | 医生自动审批(仅开发环境建议开启)                  |
| `MILVUS_HOST`         | `milvus`(容器内)/ `localhost`(本地) | Milvus 向量库地址                       |
| `MILVUS_PORT`         | `19530`                      | Milvus 向量库端口                        |
| `RAG_MODEL`           | `paraphrase-multilingual-MiniLM-L12-v2` | 向量嵌入模型(首次启动自动下载)         |

## 测试

```bash
# PoC 验证 (44 项)
npm run poc:test

# 临床契约 (7 项)
npm run contracts:test

# 服务级测试 (244 项)
cd services/workflow-engine && python -m pytest -v          # 81 项
cd services/knowledge-orchestrator && python -m pytest -v   # 47 项
cd services/fhir-adapter && python -m pytest -v             # 37 项
cd services/inpatient-ward && SKIP_BRIDGE=true python -m pytest -v  # 79 项
```

**合计 295 项测试全部通过。**

## 隔离红线

- 正式代码(`apps/`、`services/`)**不得** `import` 任何 `poc/` 实现
- 唯一允许的跨目录共享: `packages/clinical-contracts-py`(Python 版)与 `packages/clinical-contracts`(JS 版)
- `poc/` 仅验证技术可行性,不代表临床有效性结论

## 路线图

- [x] PoC 验证(44 测试冻结)
- [x] 临床契约 Python 移植(v0.2.0)
- [x] 四大后端服务 + 前端联调
- [x] 临床精度 P0 修复(审计 52/100 → 修复后预估 >85)
- [x] Docker Compose 一键部署(全栈编排 + 监控 profile)
- [ ] API Gateway(路由 / 鉴权 / 统一响应)
- [ ] 病史采集 / 体格检查 / 鉴别诊断补全
- [x] Milvus Standalone 向量检索接入(etcd + minio + milvus v2.6.1)
- [ ] K8s 部署

## License

[MIT](LICENSE) © 2026 Delong Liu
