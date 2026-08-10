# 臻护 workflow-engine 镜像
# 构建上下文: 仓库根目录 (docker compose build 自动处理)
#   docker build -f services/workflow-engine/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

# 系统依赖 (健康检查)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# 共享契约包 + 服务源码 (editable 安装: 保持包内相对路径解析)
COPY packages/clinical-contracts-py /app/packages/clinical-contracts-py
COPY services/workflow-engine /app/services/workflow-engine

RUN pip install --no-cache-dir \
    -e /app/packages/clinical-contracts-py \
    -e /app/services/workflow-engine

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8100/health || exit 1

CMD ["uvicorn", "zhenhu.workflow.main:app", "--host", "0.0.0.0", "--port", "8100"]
