#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
if [ -f logs/scheduler.pid ] && kill -0 "$(cat logs/scheduler.pid)" 2>/dev/null; then
  echo "scheduler 已在运行，PID=$(cat logs/scheduler.pid)"
  exit 0
fi
nohup python scheduler.py > logs/scheduler.log 2>&1 &
echo $! > logs/scheduler.pid
echo "scheduler 已启动，PID=$(cat logs/scheduler.pid)"
echo "日志：logs/scheduler.log"
