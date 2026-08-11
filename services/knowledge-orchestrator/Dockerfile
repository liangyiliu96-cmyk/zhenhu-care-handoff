# 臻护 knowledge-orchestrator 镜像
# 构建上下文: 仓库根目录 (docker compose build 自动处理)
#   docker build -f services/knowledge-orchestrator/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

# 系统依赖 (健康检查)
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# 共享契约包 + 服务源码 (editable 安装)
COPY packages/clinical-contracts-py /app/packages/clinical-contracts-py
COPY services/knowledge-orchestrator /app/services/knowledge-orchestrator

RUN pip install --no-cache-dir \
    -e /app/packages/clinical-contracts-py \
    -e /app/services/knowledge-orchestrator

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8200/health || exit 1

CMD ["uvicorn", "zhenhu.knowledge.main:app", "--host", "0.0.0.0", "--port", "8200"]
