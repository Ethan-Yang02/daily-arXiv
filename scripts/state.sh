#!/bin/bash
# 查看调度器状态 / Show scheduler status
PID_FILE="logs/scheduler.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ Scheduler running (PID: $PID)"
        ps -fp "$PID"
    else
        echo "⚠️  Stale PID file (process $PID not found)"
    fi
else
    echo "⚠️  Scheduler not running"
fi
