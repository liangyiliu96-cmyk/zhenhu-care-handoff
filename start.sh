#!/bin/bash
# 臻护后端一键启动 — 阶段 0 本地开发
# 用法: bash start.sh        启动三服务
#       bash start.sh test   启动后运行集成测试

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== 臻护后端启动 ==="

# 安装依赖（仅首次需要）
pip install -e packages/clinical-contracts-py -q 2>/dev/null || true
pip install -e services/workflow-engine -q 2>/dev/null || true
pip install -e services/knowledge-orchestrator -q 2>/dev/null || true
pip install -e services/fhir-adapter -q 2>/dev/null || true

# 清理上次运行的数据库文件
rm -f /tmp/zhenhu-*.db 2>/dev/null

echo ""
echo "启动服务..."
echo "  workflow-engine       → http://localhost:8100"
echo "  knowledge-orchestrator → http://localhost:8200"
echo "  fhir-adapter           → http://localhost:8300"
echo ""

# 并行启动三个服务
uvicorn zhenhu.workflow.main:app --host 0.0.0.0 --port 8100 --log-level warning &
PID1=$!

# knowledge-orchestrator 需要知道 workflow-engine 的位置（跨服务 hook）
WORKFLOW_ENGINE_URL=http://localhost:8100/hooks/knowledge-changed \
  uvicorn zhenhu.knowledge.main:app --host 0.0.0.0 --port 8200 --log-level warning &
PID2=$!

uvicorn zhenhu.fhir.main:app --host 0.0.0.0 --port 8300 --log-level warning &
PID3=$!

# 等待全部就绪
echo "等待服务就绪..."
for i in 1 2 3 4 5; do
  if curl -s http://localhost:8100/health >/dev/null 2>&1 && \
     curl -s http://localhost:8200/health >/dev/null 2>&1 && \
     curl -s http://localhost:8300/health >/dev/null 2>&1; then
    echo "✅ 三个服务全部就绪"
    break
  fi
  sleep 2
done

echo ""
echo "端点速查:"
echo "  curl http://localhost:8100/health"
echo "  curl http://localhost:8200/health"
echo "  curl http://localhost:8300/health"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 运行集成测试
if [ "$1" = "test" ]; then
  echo ""
  echo "=== 运行集成测试 ==="
  python "$ROOT/scripts/integration_test.py"
fi

# 等待任一进程退出
wait
