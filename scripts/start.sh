#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ">>> 启动后端 (uv) ..."
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  uv sync
fi
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACK_PID=$!

echo ">>> 启动前端三端 (pnpm) ..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  pnpm install
fi
pnpm run dev &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null' EXIT

echo ""
echo "=========================================="
echo "  医生端:   http://localhost:5173"
echo "  候诊大屏: http://localhost:5174"
echo "  患者 H5:  http://localhost:5175"
echo "  API:      http://localhost:8000/docs"
echo "=========================================="
wait
