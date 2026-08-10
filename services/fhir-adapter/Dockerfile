# 臻护 fhir-adapter 镜像
# 构建上下文: 仓库根目录 (docker compose build 自动处理)
#   docker build -f services/fhir-adapter/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

# 系统依赖 (健康检查)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# 共享契约包 + 服务源码 (editable 安装)
COPY packages/clinical-contracts-py /app/packages/clinical-contracts-py
COPY services/fhir-adapter /app/services/fhir-adapter

RUN pip install --no-cache-dir \
    -e /app/packages/clinical-contracts-py \
    -e /app/services/fhir-adapter

# FHIR 适配器运行数据目录
RUN mkdir -p /var/lib/zhenhu

EXPOSE 8300

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8300/health || exit 1

CMD ["uvicorn", "zhenhu.fhir.main:app", "--host", "0.0.0.0", "--port", "8300"]
