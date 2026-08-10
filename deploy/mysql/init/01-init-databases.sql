-- 臻护平台 MySQL 三库隔离初始化
-- 挂载至 /docker-entrypoint-initdb.d/, 首次启动自动执行
-- 注意: zhenhu_workflow 由 MYSQL_DATABASE 环境变量创建, 此处补齐其余两库并授权

CREATE DATABASE IF NOT EXISTS zhenhu_workflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS zhenhu_knowledge CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS zhenhu_fhir CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 授权 (用户由 MySQL 镜像 MYSQL_USER 创建, 此处补齐三库权限)
GRANT ALL PRIVILEGES ON zhenhu_workflow.* TO 'zhenhu'@'%';
GRANT ALL PRIVILEGES ON zhenhu_knowledge.* TO 'zhenhu'@'%';
GRANT ALL PRIVILEGES ON zhenhu_fhir.* TO 'zhenhu'@'%';
FLUSH PRIVILEGES;
