#!/bin/bash
# 臻护平台一键启动 —— 4服务后台启动 + 健康检查
# 用法: SKIP_BRIDGE=true bash start.sh

set -e
PYTHON=C:/Users/Windows/.workbuddy/binaries/python/versions/3.13.12/python.exe
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== 臻护平台启动 ==="

# 环境变量默认值
export SKIP_BRIDGE="${SKIP_BRIDGE:-false}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
export FHIR_ADAPTER_URL="${FHIR_ADAPTER_URL:-http://127.0.0.1:8300/fhir}"
INPATIENT_PORT="${INPATIENT_PORT:-8001}"

# Python 路径: 使各服务能找到自己的 zhenhu 包 + 共享 contracts 包
export PYTHONPATH="$ROOT/services/inpatient-ward/src:$ROOT/services/fhir-adapter/src:$ROOT/packages/clinical-contracts-py/src"

echo "SKIP_BRIDGE=$SKIP_BRIDGE (false=启用FHIR同步)"
echo "DEEPSEEK_API_KEY=$([ -n "$DEEPSEEK_API_KEY" ] && echo '已设置' || echo '未设置(使用规则引擎)')"
echo "FHIR_ADAPTER_URL=$FHIR_ADAPTER_URL"

# 1. workflow-engine (8100)
echo ""
echo "[1/5] 启动 workflow-engine (8100)..."
cd "$ROOT/services/workflow-engine"
PYTHONPATH="$ROOT/services/workflow-engine/src:$PYTHONPATH" $PYTHON -m uvicorn zhenhu.workflow.main:app --host 0.0.0.0 --port 8100 &
sleep 2

# 2. knowledge-orchestrator (8200)
echo "[2/5] 启动 knowledge-orchestrator (8200)..."
cd "$ROOT/services/knowledge-orchestrator"
PYTHONPATH="$ROOT/services/knowledge-orchestrator/src:$PYTHONPATH" $PYTHON -m uvicorn zhenhu.knowledge.main:app --host 0.0.0.0 --port 8200 &
sleep 2

# 3. fhir-adapter (8300)
echo "[3/5] 启动 fhir-adapter (8300)..."
cd "$ROOT/services/fhir-adapter"
$PYTHON -m uvicorn zhenhu.fhir.main:app --host 127.0.0.1 --port 8300 &
sleep 2

# 4. inpatient-ward (宿主机 ${INPATIENT_PORT}，容器内 8000) — FHIR 同步已接入
echo "[4/5] 启动 inpatient-ward (${INPATIENT_PORT})..."
cd "$ROOT/services/inpatient-ward"
$PYTHON -m uvicorn zhenhu.inpatient.main:app --host 127.0.0.1 --port "$INPATIENT_PORT" &
sleep 3

# 健康检查
echo ""
echo "=== 健康检查 ==="
for port in 8100 8200 8300 "$INPATIENT_PORT"; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health" 2>/dev/null || echo "DOWN")
    echo "  :$port -> $status"
done

echo ""
echo "=== 臻护平台已启动 ==="
echo "  inpatient-ward  API: http://127.0.0.1:${INPATIENT_PORT}"
echo "  fhir-adapter     : http://localhost:8300"
echo "  API文档(Swagger) : http://127.0.0.1:${INPATIENT_PORT}/docs"
echo "  Metrics          : http://127.0.0.1:${INPATIENT_PORT}/metrics"
echo "  FHIR 适配器文档   : http://localhost:8300/docs"
echo "  停止:             kill %1 %2 %3 %4"
