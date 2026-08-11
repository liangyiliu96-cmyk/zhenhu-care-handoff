# 臻护 inpatient-ward (住院协同) 镜像
# 构建上下文: 仓库根目录 (docker compose build 自动处理)
#   docker build -f services/inpatient-ward/Dockerfile .
# 注意: 采用 editable 安装以保留 config/ 与 disease_templates/ 的相对路径解析。
FROM python:3.12-slim

WORKDIR /app

# 系统依赖 (健康检查)
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# 共享契约包 + 服务源码 (必须先装 contracts, 再装服务)
COPY packages/clinical-contracts-py /app/packages/clinical-contracts-py
COPY services/inpatient-ward /app/services/inpatient-ward

RUN pip install --no-cache-dir -e /app/packages/clinical-contracts-py \
    && pip install --no-cache-dir -r /app/services/inpatient-ward/requirements.txt \
    && pip install --no-cache-dir -e /app/services/inpatient-ward

# 模型预缓存 (P3): 构建期预下载 sentence-transformers 模型, 使运行时 HF_HUB_OFFLINE=1 可离线加载。
#   - rag_engine 仅在加载时 setdefault("HF_HUB_OFFLINE","1"), 不覆盖 HF_HOME,
#     因此 ENV HF_HOME 会同时作用于构建期 RUN 与运行时容器, 运行时能命中此缓存目录。
#   - || true 兜底: 构建环境无外网时不阻断镜像构建 (运行时 rag_engine 会回退 TF-IDF)。
#   - 镜像体积增加约 ~130MB (paraphrase-multilingual-MiniLM-L12-v2)。
ENV HF_HOME=/app/.hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')" || true

# 状态数据目录 (compose 挂卷持久化)
RUN mkdir -p /var/lib/zhenhu

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "zhenhu.inpatient.main:app", "--host", "0.0.0.0", "--port", "8000"]
