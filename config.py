"""
config.py — Environment-based configuration for top50scraper bot.
"""

import os


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        raise EnvironmentError(f"Env var '{key}' must be a number. Got: {os.environ.get(key)!r}")


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        raise EnvironmentError(f"Env var '{key}' must be an integer. Got: {os.environ.get(key)!r}")


# ─────────────────────────────────────────────
# Required
# ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise EnvironmentError(
        "TELEGRAM_BOT_TOKEN is not set.\n"
        "Export it before starting: export TELEGRAM_BOT_TOKEN=your_token"
    )

# ─────────────────────────────────────────────
# Filter defaults
# ─────────────────────────────────────────────

DEFAULT_MIN_WIN_RATE: float   = _float("DEFAULT_MIN_WIN_RATE", 60.0)
DEFAULT_MIN_TRANSACTIONS: int = _int("DEFAULT_MIN_TRANSACTIONS", 5)
SCRAPE_LIMIT: int             = _int("SCRAPE_LIMIT", 50)

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

_base = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.environ.get("DATA_DIR", os.path.join(_base, "data"))
LOG_DIR: str  = os.environ.get("LOG_DIR",  os.path.join(_base, "logs"))

# ─────────────────────────────────────────────
# Chain configuration
# ─────────────────────────────────────────────
# Each entry:
#   rpc_url       — public RPC endpoint for native balance checks
#   native_symbol — symbol shown in CSV balance column
#   gmgn_chain    — chain identifier used in GMGN API URLs
#   address_type  — "solana" or "evm"
#   chain_id      — EVM chain ID (None for Solana)
# ─────────────────────────────────────────────

CHAIN_CONFIG: dict[str, dict] = {
    "sol": {
        "rpc_url":       os.environ.get("SOL_RPC_URL",  "https://api.mainnet-beta.solana.com"),
        "native_symbol": "SOL",
        "gmgn_chain":    "sol",
        "address_type":  "solana",
        "chain_id":      None,
    },
    "eth": {
        "rpc_url":       os.environ.get("ETH_RPC_URL",  "https://eth.llamarpc.com"),
        "native_symbol": "ETH",
        "gmgn_chain":    "eth",
        "address_type":  "evm",
        "chain_id":      1,
    },
    "bsc": {
        "rpc_url":       os.environ.get("BSC_RPC_URL",  "https://bsc-dataseed1.binance.org"),
        "native_symbol": "BNB",
        "gmgn_chain":    "bsc",
        "address_type":  "evm",
        "chain_id":      56,
    },
    "base": {
        "rpc_url":       os.environ.get("BASE_RPC_URL", "https://mainnet.base.org"),
        "native_symbol": "ETH",
        "gmgn_chain":    "base",
        "address_type":  "evm",
        "chain_id":      8453,
    },
}

# Detection order for EVM chains (checked in this sequence via eth_getCode)
EVM_DETECTION_ORDER: list[str] = ["eth", "bsc", "base"]
