# 臻护架构文档

| 编号 | 文档 | 说明 |
|------|------|------|
| 00 | 系统架构总览 | FastAPI+MySQL/Milvus, 5服务架构 |
| 01 | 数据模型与存储方案 | 20+表, MySQL三库+Milvus+Redis |
| 02 | 服务拆分与模块边界 | 5服务职责+通信约束 |
| 03 | 接口契约与API设计 | 29端点+UnifiedResponse |
| 04 | 身份鉴权与权限体系 | Keycloak OIDC+5角色 |
| 05 | FHIR适配与医院集成 | 8表映射+Patient Compartment |
| 06 | LLM Agent 工程管线 | 5Agent+模型路由+溯源 |
| 07 | 可观测性与运维方案 | 日志/告警/CI/CD |
| 08 | Cardio改造方案 | 废案→通用住院协同, 9阶段 |
| 09 | Cardio改造成果说明 | 已合并至 inpatient-ward |

Mermaid 图表见 `diagrams/` 子目录。
