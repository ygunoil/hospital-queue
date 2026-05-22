#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/.hospital-dev.pids"

PORT=8000
if [ -f "$ROOT/backend/.env" ]; then
  val=$(grep -E '^PORT=' "$ROOT/backend/.env" | tail -1 | cut -d= -f2 | tr -d ' "\r' || true)
  [ -n "${val:-}" ] && PORT="$val"
fi

# 检测 8000 是否被其他程序占用（非本项目的 /api/health 响应）
if lsof -ti tcp:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  if ! curl -sf "http://127.0.0.1:8000/api/health" 2>/dev/null | grep -q 'llm_mock'; then
    echo ">>> 提示: 8000 端口已被其他服务占用 (非本叫号后端)，本项目使用端口 ${PORT}"
    [ "$PORT" = "8000" ] && PORT=8000
  fi
fi

export BACKEND_PORT="$PORT"

echo ">>> 启动后端 (uv) 端口 ${PORT} ..."
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  uv sync
fi
uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload &
BACK_PID=$!

echo ">>> 启动前端三端 (pnpm)，API 代理 -> 127.0.0.1:${PORT} ..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  pnpm install
fi
BACKEND_PORT="$PORT" pnpm run dev &
FRONT_PID=$!

echo "$BACK_PID backend" > "$PID_FILE"
echo "$FRONT_PID frontend" >> "$PID_FILE"

cleanup() {
  kill $BACK_PID $FRONT_PID 2>/dev/null || true
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

echo ""
echo "=========================================="
echo "  医生端:   http://localhost:5173"
echo "  候诊大屏: http://localhost:5174"
echo "  患者 H5:  http://localhost:5175"
echo "  API:      http://127.0.0.1:${PORT}/docs"
echo "=========================================="
echo "  停止服务: ./scripts/stop.sh  或 Ctrl+C"
echo "=========================================="
wait
