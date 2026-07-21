FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY src/ src/
COPY config/ config/
COPY disease_templates/ src/zhenhu/inpatient/disease_templates/

# 端口
EXPOSE 8000

# 启动
CMD ["python", "-m", "uvicorn", "zhenhu.inpatient.main:app", "--host", "0.0.0.0", "--port", "8000"]
