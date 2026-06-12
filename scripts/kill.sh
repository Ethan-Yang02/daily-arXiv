#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f logs/scheduler.pid ]; then
  echo "未找到 logs/scheduler.pid，scheduler 可能未运行。"
  exit 0
fi
PID="$(cat logs/scheduler.pid)"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "已停止 scheduler，PID=$PID"
else
  echo "PID=$PID 不存在，清理 pid 文件。"
fi
rm -f logs/scheduler.pid
