#!/bin/bash
# 停止调度器 / Stop scheduler
PID_FILE="logs/scheduler.pid"
if [ -f "$PID_FILE" ]; then
    kill $(cat "$PID_FILE") 2>/dev/null && echo "✅ Scheduler stopped" || echo "⚠️  Process not found"
    rm -f "$PID_FILE"
else
    echo "⚠️  No PID file found"
fi
