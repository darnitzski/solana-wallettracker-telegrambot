# top50scraper

A Telegram bot that scans [GMGN.ai](https://gmgn.ai) for the top 50 traders on any Solana memecoin token, filters them by win rate and activity, and delivers the results as a downloadable CSV.

---

## Project Structure

```
top50scraper/
├── bot.py           — Telegram bot (commands, handlers)
├── scraper.py       — GMGN.ai data fetcher (curl_cffi, retry logic)
├── analyzer.py      — Filter, rank, and export trader data to CSV
├── config.py        — Environment variable configuration
├── requirements.txt — Python dependencies
├── run.sh           — Start the bot (sets up venv, installs deps, launches)
├── stop.sh          — Stop the bot gracefully
├── data/            — Generated CSV files (auto-created)
└── logs/            — Bot log files (auto-created)
    └── telegram_bot.log
```

---

## Setup

### 1. Prerequisites

- Python 3.10+
- A Linux/macOS server (or WSL on Windows)
- A Telegram bot token (see below)

### 2. Get a Telegram Bot Token from BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts — choose a name and username for your bot
4. BotFather will give you a token like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
5. Copy that token — you'll need it in the next step

### 3. Configure Environment Variables

Set your bot token before running:

```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
```

Or add it directly to `run.sh` in the `TELEGRAM_BOT_TOKEN` line.

All available variables:

| Variable                  | Default   | Description                                      |
|---------------------------|-----------|--------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`      | *(required)* | Your Telegram bot token from BotFather         |
| `DEFAULT_MIN_WIN_RATE`    | `60.0`    | Default minimum win rate % filter               |
| `DEFAULT_MIN_TRANSACTIONS`| `5`       | Default minimum transaction count filter        |
| `SCRAPE_LIMIT`            | `50`      | Number of traders to fetch from GMGN per scan   |
| `DATA_DIR`                | `./data`  | Directory to save CSV files                     |
| `LOG_DIR`                 | `./logs`  | Directory for log files                         |

### 4. Start the Bot

```bash
# Make scripts executable (first time only)
chmod +x run.sh stop.sh

# Start
./run.sh
```

The script will:
- Create a Python virtual environment in `venv/`
- Install all dependencies from `requirements.txt`
- Create `data/` and `logs/` directories
- Launch the bot in the background with `nohup`
- Write the process PID to `bot.pid`

### 5. Stop the Bot

```bash
./stop.sh
```

### 6. View Logs

```bash
tail -f logs/telegram_bot.log
```

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and usage overview |
| `/scan <contract_address>` | Scan top traders for a Solana token |
| `/setfilter <min_win_rate> <min_txs>` | Update filter thresholds for your session |
| `/filters` | Show your current filter settings |
| `/help` | List all commands |

### Example

```
/scan EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm
```

The bot will:
1. Fetch the top 50 traders for the token from GMGN.ai
2. Filter by your current win rate and transaction thresholds
3. Rank the remaining traders
4. Send you a CSV file with full details + a summary caption

### Adjusting Filters

```
/setfilter 40 10
```

Sets minimum win rate to 40% and minimum transactions to 10 for your session.
Filters reset to defaults when the bot restarts.

---

## CSV Output Format

Each scan produces a CSV file in `data/` named `{TOKEN}_{YYYYMMDD_HHMMSS}.csv`:

| Column | Description |
|--------|-------------|
| Rank | Position after filtering and sorting |
| Wallet Address | Solana wallet address |
| Win Rate % | Profit/cost ratio as a percentage |
| PnL USD | Total profit/loss in USD |
| Realized Profit USD | Realized profit in USD |
| Total Transactions | Total buy + sell transaction count |

---

## How It Works

1. **scraper.py** — Uses `curl_cffi` to impersonate Chrome's TLS fingerprint, bypassing Cloudflare protection on GMGN.ai. Hits the `/vas/api/v1/token_traders/sol/{address}` endpoint with retry logic.

2. **analyzer.py** — Filters traders by win rate and activity thresholds, sorts by win rate → tx count → realized profit, assigns ranks, and exports to CSV.

3. **bot.py** — Telegram bot that ties it together. Stores per-user filter preferences in memory for the session.

---

## Troubleshooting

**Bot doesn't start:**
- Check `logs/telegram_bot.log` for errors
- Make sure `TELEGRAM_BOT_TOKEN` is set correctly

**Scan returns no results:**
- The token may be too new or have low trading volume on GMGN
- Try lowering filters: `/setfilter 10 1`
- Double-check the contract address

**Cloudflare errors:**
- GMGN occasionally changes their bot protection
- The scraper uses `curl_cffi` Chrome impersonation which handles most cases
- If persistent, try again after a few minutes
