# Contributing to 臻护 (Zhenhu)

欢迎贡献!臻护是全病程数智医护平台,遵循开放协作与**临床安全优先**原则。

## 快速开始

```bash
# 安装依赖 (Python 3.12+ / Node 22+)
python -m venv .venv && source .venv/bin/activate
pip install -e packages/clinical-contracts-py
pip install -e "services/inpatient-ward[dev]"

# 运行测试
cd services/inpatient-ward && python -m pytest -q   # 各服务同法
cd apps/frontend && npm install && npm run test:run
```

## 提交前检查

- ✅ `ruff check services/*/src` 全绿(配置见 `ruff.toml`)
- ✅ 后端 pytest 全量通过(workflow 90 / knowledge 49 / fhir 42 / inpatient 374)
- ✅ 前端 vitest 全量通过(179)
- ✅ 不引入 `poc/` 目录引用(隔离红线,见 README)
- ✅ 不提交 `.env`(密钥)与 `docs/`(本地文档,见 .gitignore)

## 分支与流程

1. 从 `main` 切分支:`git checkout -b feat/your-feature`
2. 提交信息遵循 Conventional Commits:`feat:` / `fix:` / `docs:` / `chore:`
3. 推送并创建 **Pull Request**(main 分支有 CI 检查保护,必须全绿)
4. 至少 1 位维护者 review 后合入

## 临床安全准则

- 所有 AI 输出必须可追溯(引用来源)、可审核(审计日志)
- 不直接执行临床动作;医生/护士掌握最终决策
- 涉及患者数据的功能须遵循最小化原则与隐私保护

## 报告问题

使用 Issue 模板;安全问题走 [SECURITY.md](SECURITY.md)。
