"""
analyzer.py — Trader data filter, ranker, and CSV exporter for top50scraper.
"""

import csv
import os
from datetime import datetime

import config

DUST_THRESHOLD = 0.001  # native token units — wallets below this are considered zero-balance


def filter_and_rank(
    traders: list[dict],
    min_win_rate: float = 60.0,
    min_transactions: int = 5,
    exclude_zero_balance: bool = True,
) -> tuple[list[dict], int]:
    """
    Filter and rank trader dicts from scraper.fetch_top_traders().

    Filtering (in order):
        1. exclude_zero_balance: removes wallets with native_balance <= DUST_THRESHOLD
        2. min_win_rate:         removes wallets with win_rate_pct < min_win_rate
        3. min_transactions:     removes wallets with tx_count < min_transactions

    Sorting (descending):
        1. win_rate_pct
        2. tx_count
        3. realized_profit_usd

    Adds 'rank' field (1-indexed) to each surviving dict.

    Returns:
        (ranked_list, zero_balance_removed_count)
    """
    zero_balance_removed = 0
    if exclude_zero_balance:
        before = len(traders)
        traders = [t for t in traders if (t.get("native_balance") or 0) > DUST_THRESHOLD]
        zero_balance_removed = before - len(traders)

    filtered = [
        t for t in traders
        if (t.get("win_rate_pct") or 0) >= min_win_rate
        and (t.get("tx_count") or 0) >= min_transactions
    ]

    filtered.sort(
        key=lambda t: (
            t.get("win_rate_pct") or 0,
            t.get("tx_count") or 0,
            t.get("realized_profit_usd") or 0,
        ),
        reverse=True,
    )

    for i, trader in enumerate(filtered, 1):
        trader["rank"] = i

    return filtered, zero_balance_removed


def generate_csv(traders: list[dict], token_ticker: str, chain: str) -> str:
    """
    Write ranked trader data to:
        data/{chain}_{token_ticker}_{YYYYMMDD_HHMMSS}.csv

    Columns:
        Rank, Chain, Wallet Address, Win Rate % (30d), PnL USD,
        Realized Profit USD, Total Transactions, <NativeSymbol> Balance

    The balance column header is named dynamically per chain:
        SOL Balance (sol), BNB Balance (bsc), ETH Balance (eth/base)

    Returns absolute file path.
    """
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_ticker = token_ticker.replace("/", "_").replace("\\", "_")
    filename    = f"{chain}_{safe_ticker}_{timestamp}.csv"
    filepath    = os.path.join(data_dir, filename)

    native_sym     = config.CHAIN_CONFIG.get(chain, {}).get("native_symbol", "NATIVE")
    balance_header = f"{native_sym} Balance"

    fieldnames = [
        "Rank",
        "Chain",
        "Wallet Address",
        "Win Rate % (30d)",
        "PnL USD",
        "Realized Profit USD",
        "Total Transactions",
        balance_header,
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in traders:
            writer.writerow({
                "Rank":               t.get("rank", ""),
                "Chain":              chain.upper(),
                "Wallet Address":     t.get("wallet_address", ""),
                "Win Rate % (30d)":   t.get("win_rate_pct", 0),
                "PnL USD":            t.get("pnl_usd", 0),
                "Realized Profit USD": t.get("realized_profit_usd", 0),
                "Total Transactions": t.get("tx_count", 0),
                balance_header:       t.get("native_balance", 0),
            })

    return os.path.abspath(filepath)
