# clinical-contracts-py

臻护平台 Python 版临床契约包(v0.2.0)—— 正式工程共享基础库,是病例/知识/入库任务状态机的**唯一事实来源**。

> 隔离红线:正式代码(`apps/`、`services/`)不得 `import` 任何 `poc/` 实现,唯一允许的跨目录共享即本包。

## 内容

- **状态机枚举**:病例状态 (`CaseState`)、知识版本状态、入库任务状态 —— 对照《需求规格说明书 v0.2》§3.4 / §4.4,禁止调用方硬编码状态转移
- **Pydantic v2 模型**:临床契约数据模型与校验
- **SQLAlchemy 2.0 async 基础设施**:`create_async_engine` / `async_sessionmaker` / `get_session` 统一封装,开发测试默认 SQLite `:memory:`

## 安装

```bash
pip install -e packages/clinical-contracts-py
```

## 使用

```python
from zhenhu.contracts import CaseState, get_session

# 状态机: draft → analysing → review_pending → confirmed / rejected
```

## 与 JS 版的关系

| 版本 | 位置 | 用途 |
|---|---|---|
| v0.1.0 (JS) | `packages/clinical-contracts` | PoC 验证区使用 |
| v0.2.0 (Python, 本包) | `packages/clinical-contracts-py` | 正式工程使用,唯一事实来源 |
