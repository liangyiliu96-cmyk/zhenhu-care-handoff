# 臻护后端服务 Docker 镜像
# 用法: docker build --build-arg SERVICE=workflow-engine -t zhenhu-workflow .

FROM python:3.13-slim

ARG SERVICE
ENV SERVICE=${SERVICE}

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi>=0.115 \
    uvicorn[standard] \
    sqlalchemy[asyncio]>=2.0 \
    aiosqlite \
    pydantic>=2.0 \
    httpx \
    celery>=5.4 \
    redis>=5.2

WORKDIR /app

# 复制共享契约包
COPY packages/clinical-contracts-py /app/packages/clinical-contracts-py
RUN pip install -e /app/packages/clinical-contracts-py

# 复制目标服务代码
COPY services/${SERVICE} /app/service
RUN pip install -e /app/service

# 数据持久化目录
RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/service.db

EXPOSE 8000

CMD ["sh", "-c", "uvicorn zhenhu.${SERVICE//-/_}.main:app --host 0.0.0.0 --port 8000"]
