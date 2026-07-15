# 臻护 · 出院交接与慢病智能协同管理平台

面向医护人员的临床决策支持系统 (CDSS)，通过受控知识库和多 Agent 工作流，发现出院交接与院后随访中的信息缺漏、冲突和规范风险。

## 项目结构

```
zhenhu-care-handoff/
├── docs/                    # 项目级文档
│   ├── requirements/        #   需求规格 v0.2 + 证据基线 v0.1 + 对齐报告
│   └── architecture/        #   正式工程架构设计
├── packages/                # 共享包（正式 + PoC 共同引用）
│   └── clinical-contracts/  #   状态机契约（唯一事实来源）
├── apps/                    # 前端应用（正式工程）
├── services/                # 后端服务（正式工程）
│   └── knowledge-orchestrator/  # 知识编排服务（骨架）
├── tests/                   # 正式工程测试
├── poc/                     # PoC 验证区（独立，不 import 正式代码）
└── 参考借鉴项目/             # 外部参考（只读，不入版本管理）
```

## 当前阶段

**阶段 0：需求寻找**——需求基线已建立，PoC 44/44 测试验证通过。正式工程设计待启动。

## 快速开始

```bash
# PoC 验证
npm run poc:test          # 44/44 单元测试
npm run poc:serve         # 启动 PoC 演示服务 (http://127.0.0.1:4173)

# 契约测试
npm run contracts:test    # 临床契约测试 (7/7)
```

## 隔离红线

- 正式代码 (`apps/`、`services/`) 不得 import `poc/` 实现
- 唯一共享：`packages/clinical-contracts`
- PoC 仅验证技术可行性，不证明临床有效性
