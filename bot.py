"""
bot.py — Telegram bot for top50scraper (multi-chain).
Supports Solana, Ethereum, BNB Chain, and Base.
Chain is auto-detected from contract address format.
"""

import os
import re
import logging
import sys
from logging.handlers import RotatingFileHandler

from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from scraper import fetch_top_traders, detect_chain, ScraperError
from analyzer import filter_and_rank, generate_csv
import config


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_fh  = RotatingFileHandler(os.path.join(LOG_DIR, "telegram_bot.log"),
                            maxBytes=5 * 1024 * 1024, backupCount=3)
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Per-session filter state
# ─────────────────────────────────────────────

DEFAULT_FILTERS = {
    "min_win_rate":         config.DEFAULT_MIN_WIN_RATE,
    "min_transactions":     config.DEFAULT_MIN_TRANSACTIONS,
    "exclude_zero_balance": True,
}
user_filters: dict[int, dict] = {}


def get_filters(chat_id: int) -> dict:
    return user_filters.get(chat_id, DEFAULT_FILTERS.copy())


# ─────────────────────────────────────────────
# Address validation (any supported format)
# ─────────────────────────────────────────────

def is_plausible_address(address: str) -> bool:
    """Accept Solana base58 OR EVM 0x addresses."""
    return bool(
        re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address)   # Solana
        or re.match(r"^0x[0-9a-fA-F]{40}$", address)            # EVM
    )


# ─────────────────────────────────────────────
# Chain display helpers
# ─────────────────────────────────────────────

CHAIN_EMOJI = {
    "sol":  "◎",
    "eth":  "⟠",
    "bsc":  "🟡",
    "base": "🔵",
}

CHAIN_LABEL = {
    "sol":  "Solana",
    "eth":  "Ethereum",
    "bsc":  "BNB Chain",
    "base": "Base",
}


# ─────────────────────────────────────────────
# Bot command definitions
# ─────────────────────────────────────────────

BOT_COMMANDS = [
    BotCommand("start",      "Welcome message and usage guide"),
    BotCommand("scan",       "Scan top 50 traders for a token (auto-detects chain)"),
    BotCommand("setfilter",  "Set min win rate and min transactions"),
    BotCommand("togglezero", "Toggle zero-balance wallet filter on/off"),
    BotCommand("filters",    "Show your current filter settings"),
    BotCommand("help",       "Show all commands and usage"),
]

HELP_TEXT = """
📋 *Available Commands*

/start — Welcome & overview
/scan `<contract_address>` — Scan top 50 traders (chain auto-detected)
/setfilter `<min_win_rate> <min_txs>` — Update filter thresholds
/togglezero — Toggle zero-balance wallet filter on/off
/filters — Show your current filter settings
/help — Show this list

*Supported chains (auto-detected):*
◎ Solana — base58 address, 32–44 chars
⟠ Ethereum — 0x address
🟡 BNB Chain — 0x address
🔵 Base — 0x address

*Examples:*
`/scan Cm6fNnMk7NfzStP9CZpsQA2v3jjzbcYGAxdJySmHpump`
`/scan 0x6982508145454Ce325dDbE47a25d4ec3d2311933`
`/setfilter 50 10`
"""

WELCOME_TEXT = """
👋 *Welcome to Top50Scraper Bot!*

I scan GMGN.ai for the top 50 traders on any token and deliver results as a ranked CSV.

*Chain detection is automatic* — just paste any contract address and I'll figure out the chain.

*Supported chains:*
◎ Solana (SOL)
⟠ Ethereum (ETH)
🟡 BNB Chain (BNB)
🔵 Base (ETH)

*How to use:*
1️⃣ `/scan <contract_address>` — auto-detect chain, fetch top 50 traders, export CSV
2️⃣ `/setfilter <win_rate> <min_txs>` — adjust filter thresholds
3️⃣ `/togglezero` — exclude/include wallets with zero native balance

*Default filters:*
• Min win rate: 60%
• Min transactions: 5
• Zero-balance filter: ON

Use /help to see all commands.
"""


# ─────────────────────────────────────────────
# post_init: register command menu
# ─────────────────────────────────────────────

async def post_init(application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Telegram command menu registered.")


# ─────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_filters(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    f = get_filters(update.effective_chat.id)
    zero_status = "ON ✅" if f["exclude_zero_balance"] else "OFF ❌"
    await update.message.reply_text(
        f"⚙️ *Your current filters:*\n"
        f"• Min win rate: `{f['min_win_rate']}%`\n"
        f"• Min transactions: `{f['min_transactions']}`\n"
        f"• Zero-balance filter: {zero_status}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_setfilter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(ctx.args) != 2:
        await update.message.reply_text(
            "❌ Usage: `/setfilter <min_win_rate> <min_transactions>`\nExample: `/setfilter 50 10`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    try:
        min_wr = float(ctx.args[0])
        min_tx = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("❌ Both values must be numbers.", parse_mode=ParseMode.MARKDOWN)
        return
    if not (0 <= min_wr <= 10000):
        await update.message.reply_text("❌ `min_win_rate` must be 0–10000.", parse_mode=ParseMode.MARKDOWN)
        return
    if min_tx < 0:
        await update.message.reply_text("❌ `min_transactions` must be ≥ 0.", parse_mode=ParseMode.MARKDOWN)
        return
    f = get_filters(chat_id)
    f["min_win_rate"] = min_wr
    f["min_transactions"] = min_tx
    user_filters[chat_id] = f
    logger.info(f"chat_id={chat_id} setfilter wr>={min_wr}% tx>={min_tx}")
    await update.message.reply_text(
        f"✅ *Filters updated:*\n• Min win rate: `{min_wr}%`\n• Min transactions: `{min_tx}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_togglezero(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    f = get_filters(chat_id)
    f["exclude_zero_balance"] = not f["exclude_zero_balance"]
    user_filters[chat_id] = f
    if f["exclude_zero_balance"]:
        status = "ON ✅ — wallets with <0.001 native balance excluded"
    else:
        status = "OFF ❌ — zero-balance wallets included"
    logger.info(f"chat_id={chat_id} togglezero -> {f['exclude_zero_balance']}")
    await update.message.reply_text(
        f"🔄 *Zero-balance filter:* {status}", parse_mode=ParseMode.MARKDOWN
    )


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not ctx.args:
        await update.message.reply_text(
            "❌ Usage: `/scan <contract_address>`", parse_mode=ParseMode.MARKDOWN
        )
        return

    contract = ctx.args[0].strip()

    if not is_plausible_address(contract):
        await update.message.reply_text(
            "❌ Invalid contract address format.\n"
            "Expected a Solana base58 address (32–44 chars) or EVM 0x address (42 chars).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    short = f"{contract[:6]}...{contract[-4:]}"

    # ── Chain detection (fast, shown immediately) ──────────────────
    status_msg = await update.message.reply_text(
        f"🔎 Detecting chain for `{short}`...", parse_mode=ParseMode.MARKDOWN
    )

    try:
        chain = detect_chain(contract)
    except ScraperError as e:
        logger.warning(f"Chain detection failed for {contract}: {e}")
        await status_msg.edit_text(
            "❌ Could not identify the chain for this contract address. "
            "Verify the address and try again."
        )
        return

    chain_label  = CHAIN_LABEL.get(chain, chain.upper())
    chain_emoji  = CHAIN_EMOJI.get(chain, "🔗")
    native_sym   = config.CHAIN_CONFIG[chain]["native_symbol"]

    await status_msg.edit_text(
        f"{chain_emoji} *Detected chain: {chain_label}*\n"
        f"🔍 Scanning top 50 traders for `{short}`...\n"
        f"_(fetching win rates + {native_sym} balances — ~1 min)_",
        parse_mode=ParseMode.MARKDOWN,
    )

    # ── Fetch ──────────────────────────────────────────────────────
    try:
        logger.info(f"chat_id={chat_id} scanning {contract} on {chain}")
        raw_traders, detected_chain = fetch_top_traders(contract, limit=config.SCRAPE_LIMIT)
    except ScraperError as e:
        logger.warning(f"ScraperError for {contract}: {e}")
        await status_msg.edit_text(
            "❌ Failed to fetch data for this token. Check the contract address and try again."
        )
        return
    except Exception as e:
        logger.error(f"Unexpected scan error: {e}", exc_info=True)
        await status_msg.edit_text("❌ An unexpected error occurred. Please try again later.")
        return

    total_found = len(raw_traders)

    # ── Filter & rank ──────────────────────────────────────────────
    f = get_filters(chat_id)
    ranked, zero_removed = filter_and_rank(
        raw_traders,
        min_win_rate=f["min_win_rate"],
        min_transactions=f["min_transactions"],
        exclude_zero_balance=f["exclude_zero_balance"],
    )

    if not ranked:
        zero_note = f"\n_(🗑 {zero_removed} removed for zero {native_sym} balance)_" if zero_removed else ""
        await status_msg.edit_text(
            f"⚠️ No traders passed the filters.\n"
            f"Fetched: {total_found} | Passed: 0{zero_note}\n\n"
            f"Thresholds: win rate ≥ {f['min_win_rate']}%, txs ≥ {f['min_transactions']}\n"
            f"Try `/setfilter` to lower thresholds or `/togglezero` to include zero-balance wallets.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Generate CSV ───────────────────────────────────────────────
    try:
        ticker   = contract[:8].upper()
        csv_path = generate_csv(ranked, ticker, detected_chain)
    except Exception as e:
        logger.error(f"CSV generation failed: {e}", exc_info=True)
        await status_msg.edit_text("❌ Failed to generate CSV. Please try again.")
        return

    # ── Build caption ──────────────────────────────────────────────
    top3_lines = []
    for t in ranked[:3]:
        w   = t["wallet_address"]
        bal = t.get("native_balance") or 0
        top3_lines.append(
            f"  #{t['rank']} `{w[:6]}...{w[-4:]}` — "
            f"WR: {t['win_rate_pct']:.1f}% | "
            f"Realized: ${t['realized_profit_usd']:,.0f} | "
            f"{native_sym}: {bal:.3f}"
        )

    zero_line = f"\n🗑 *Removed (zero balance):* {zero_removed}" if zero_removed else ""

    caption = (
        f"✅ *Scan Complete*\n"
        f"{chain_emoji} Chain: *{chain_label}* | Token: `{short}`\n\n"
        f"📊 Total fetched: *{total_found}*\n"
        f"🎯 Passed filters: *{len(ranked)}*"
        f"{zero_line}\n"
        f"⚙️ Win rate ≥ {f['min_win_rate']}% | "
        f"Txs ≥ {f['min_transactions']} | "
        f"Zero-balance: {'ON' if f['exclude_zero_balance'] else 'OFF'}\n\n"
        f"🏆 *Top 3:*\n" + "\n".join(top3_lines)
    )

    # ── Send ───────────────────────────────────────────────────────
    await status_msg.delete()
    with open(csv_path, "rb") as csv_file:
        await update.message.reply_document(
            document=csv_file,
            filename=os.path.basename(csv_path),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    logger.info(
        f"chat_id={chat_id} sent {csv_path} "
        f"(chain={detected_chain}, {len(ranked)} traders, {zero_removed} zero-bal removed)"
    )


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting top50scraper bot (multi-chain)...")

    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("scan",       cmd_scan))
    app.add_handler(CommandHandler("setfilter",  cmd_setfilter))
    app.add_handler(CommandHandler("filters",    cmd_filters))
    app.add_handler(CommandHandler("togglezero", cmd_togglezero))

    app.run_polling(drop_pending_updates=True)
