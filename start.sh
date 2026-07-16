#!/bin/bash
# 臻护平台一键启动 —— 4服务后台启动 + 健康检查
# 用法: SKIP_BRIDGE=true bash start.sh

set -e
PYTHON=C:/Users/Windows/.workbuddy/binaries/python/versions/3.13.12/python.exe
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== 臻护平台启动 ==="

# 环境变量默认值
export SKIP_BRIDGE="${SKIP_BRIDGE:-true}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"

echo "SKIP_BRIDGE=$SKIP_BRIDGE (跳过外部HTTP服务)"
echo "DEEPSEEK_API_KEY=$([ -n "$DEEPSEEK_API_KEY" ] && echo '已设置' || echo '未设置(使用规则引擎)')"

# 1. workflow-engine (8100)
echo ""
echo "[1/4] 启动 workflow-engine (8100)..."
cd "$ROOT/services/workflow-engine"
$PYTHON -m uvicorn zhenhu.workflow.main:app --host 0.0.0.0 --port 8100 &
sleep 2

# 2. knowledge-orchestrator (8200)
echo "[2/4] 启动 knowledge-orchestrator (8200)..."
cd "$ROOT/services/knowledge-orchestrator"
$PYTHON -m uvicorn zhenhu.knowledge.main:app --host 0.0.0.0 --port 8200 &
sleep 2

# 3. fhir-adapter (8300)
echo "[3/4] 启动 fhir-adapter (8300)..."
cd "$ROOT/services/fhir-adapter"
$PYTHON -m uvicorn zhenhu.fhir.main:app --host 0.0.0.0 --port 8300 &
sleep 2

# 4. inpatient-ward (8400)
echo "[4/4] 启动 inpatient-ward (8400)..."
cd "$ROOT/services/inpatient-ward"
$PYTHON -m uvicorn zhenhu.inpatient.main:app --host 0.0.0.0 --port 8400 &
sleep 3

# 健康检查
echo ""
echo "=== 健康检查 ==="
for port in 8100 8200 8300 8400; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health" 2>/dev/null || echo "DOWN")
    echo "  :$port -> $status"
done

echo ""
echo "=== 臻护平台已启动 ==="
echo "  inpatient-ward  API: http://localhost:8400"
echo "  API文档(Swagger): http://localhost:8400/docs"
echo "  Metrics:          http://localhost:8400/metrics"
echo "  停止:             kill %1 %2 %3 %4"
