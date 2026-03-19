#!/usr/bin/env bash
# stop.sh — Stop the top50scraper Telegram bot
# Usage: ./stop.sh
# Note: chmod +x stop.sh before first use

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="bot.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  No bot.pid file found. Is the bot running?"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "⚠️  Process $PID is not running. Cleaning up stale PID file."
    rm -f "$PID_FILE"
    exit 0
fi

echo "🛑 Stopping bot (PID $PID)..."
kill "$PID"

# Wait up to 5 seconds for clean exit
for i in {1..5}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

# Force kill if still alive
if kill -0 "$PID" 2>/dev/null; then
    echo "⚠️  Process did not exit cleanly. Force killing..."
    kill -9 "$PID"
fi

rm -f "$PID_FILE"
echo "✅ Bot stopped."
