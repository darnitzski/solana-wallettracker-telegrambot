#!/usr/bin/env bash
# run.sh — Start the top50scraper Telegram bot
# Usage: ./run.sh
# Note: chmod +x run.sh before first use

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Environment ──────────────────────────────
# Export your bot token before running, or set it in your shell profile.
# Do NOT hardcode a real token here.
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN is not set. Export it before running:"
    echo "   export TELEGRAM_BOT_TOKEN=your_token_here"
    exit 1
fi

# Optional overrides (uncomment to change defaults)
# export DEFAULT_MIN_WIN_RATE=60.0
# export DEFAULT_MIN_TRANSACTIONS=5
# export SCRAPE_LIMIT=50
# export DATA_DIR="./data"
# export LOG_DIR="./logs"

# ── Check if already running ─────────────────
if [ -f bot.pid ]; then
    PID=$(cat bot.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  Bot is already running (PID $PID). Run ./stop.sh first."
        exit 1
    else
        echo "ℹ️  Stale PID file found. Cleaning up."
        rm -f bot.pid
    fi
fi

# ── Virtual environment ───────────────────────
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing/updating dependencies..."
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

# ── Directories ───────────────────────────────
mkdir -p data logs

# ── Launch ────────────────────────────────────
echo "🚀 Starting top50scraper bot..."
nohup venv/bin/python bot.py >> logs/telegram_bot.log 2>&1 &
BOT_PID=$!
echo "$BOT_PID" > bot.pid

echo "✅ Bot started (PID $BOT_PID)"
echo "   Logs: logs/telegram_bot.log"
echo "   Stop: ./stop.sh"
