# 臻护微服务层

| 服务 | 端口 | 测试 | 端点 | 说明 |
|------|------|------|------|------|
| workflow-engine | 8100 | 89 | 11 | 出院后病例状态机+审核+草稿 |
| knowledge-orchestrator | 8200 | 47 | 7 | 知识导入/混合检索/反向阻断 |
| fhir-adapter | 8300 | 41 | 5 | 医院数据映射/Patient Compartment |
| inpatient-ward | 8400 | 46 | 6 | 住院全流程(11节点Agent+7病种) |

每个服务独立 pyproject.toml, 共享 zhenhu.contracts 包。
