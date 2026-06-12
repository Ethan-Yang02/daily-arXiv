#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f logs/scheduler.pid ]; then
  echo "scheduler 未运行：未找到 logs/scheduler.pid"
  exit 0
fi
PID="$(cat logs/scheduler.pid)"
if kill -0 "$PID" 2>/dev/null; then
  ps -fp "$PID"
else
  echo "scheduler 未运行：PID=$PID 不存在"
fi
