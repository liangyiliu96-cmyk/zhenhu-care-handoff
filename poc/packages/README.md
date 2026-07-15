# 共享包目录

跨正式应用和服务复用的 TypeScript 契约、领域状态机、数据访问模型和测试夹具放在此目录。共享包不包含部署入口或界面代码，也不得以 PoC 模拟数据作为正式事实来源。

共享契约包 `@zhenhu/clinical-contracts` 已按根目录 `packages/` 约定迁移至 `packages/clinical-contracts`（正式项目共享契约的权威位置），PoC 与正式服务均从那里导入状态机与角色裁决，禁止在此处另存副本。

当前 `poc/packages/` 仅保留 PoC 专属的包（如未来需要的 PoC 模拟数据访问层），不存放跨项目共享契约。
