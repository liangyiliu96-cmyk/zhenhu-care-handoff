# 测试目录

| 位置 | 说明 |
|------|------|
| `services/*/tests/` | 各服务独立 pytest（225 passed） |
| `packages/clinical-contracts/tests/` | JS 版契约测试（PoC 验证，7/7） |
| `poc/tests/` | PoC 验证测试（冻结，44/44） |
| `tests/contracts/` | 正式工程契约测试（迁移中） |

运行：`cd services/<name> && python -m pytest -v`
