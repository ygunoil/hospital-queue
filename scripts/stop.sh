#!/usr/bin/env bash
# 停止本项目的后端与前端 dev 服务（按端口 + 可选 PID 文件）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/.hospital-dev.pids"

PORT=8000
if [ -f "$ROOT/backend/.env" ]; then
  # shellcheck disable=SC1091
  val=$(grep -E '^PORT=' "$ROOT/backend/.env" | tail -1 | cut -d= -f2 | tr -d ' "\r' || true)
  [ -n "${val:-}" ] && PORT="$val"
fi

FRONT_PORTS=(5173 5174 5175)

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "  停止端口 $port (PID: $pids)"
    kill $pids 2>/dev/null || true
    sleep 0.5
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}

echo ">>> 停止医院叫号系统 dev 服务 ..."

if [ -f "$PID_FILE" ]; then
  while read -r pid _; do
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done < "$PID_FILE"
  rm -f "$PID_FILE"
fi

kill_port "$PORT"
for p in "${FRONT_PORTS[@]}"; do
  kill_port "$p"
done

# 兜底：结束本项目目录下启动的 uvicorn / vite
pkill -f "uvicorn app.main:app.*$ROOT/backend" 2>/dev/null || true
pkill -f "$ROOT/frontend.*vite" 2>/dev/null || true

echo ">>> 已停止。若端口仍占用，可执行: lsof -i :$PORT -i :5173-5175"
echo ">>> 说明: 8000 上其他程序 (如 start_app.py) 不会被本脚本结束"
