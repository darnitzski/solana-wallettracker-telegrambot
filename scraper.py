"""
scraper.py — GMGN.ai Top Traders Scraper (multi-chain).

Supports: Solana (sol), Ethereum (eth), BNB Chain (bsc), Base (base).
Chain is auto-detected from address format — no manual input needed.

Requires:
    pip install curl_cffi

Usage:
    python scraper.py <contract_address> [limit]
    python scraper.py Cm6fNnMk7NfzStP9CZpsQA2v3jjzbcYGAxdJySmHpump 10
    python scraper.py 0x6982508145454Ce325dDbE47a25d4ec3d2311933 10
"""

import sys
import time
import json

try:
    from curl_cffi import requests as cf_requests
except ImportError:
    raise ImportError("curl_cffi is required: pip install curl_cffi")

import config


# ─────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────

class ScraperError(Exception):
    """Raised when all fetch attempts fail or chain detection fails."""
    pass


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

TOKEN_TRADERS_URL  = "https://gmgn.ai/vas/api/v1/token_traders/{chain}/{contract_address}"
WALLET_STAT_URL    = "https://gmgn.ai/pf/api/v1/wallet/{chain}/{wallet_address}/profit_stat/{period}"
WALLET_STAT_PERIOD = "30d"

GMGN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://gmgn.ai/",
    "Origin": "https://gmgn.ai",
}

MAX_RETRIES         = 3
BACKOFF_BASE        = 2    # seconds
WINRATE_FETCH_DELAY = 1.0  # seconds between win-rate calls
BALANCE_FETCH_DELAY = 0.2  # seconds between balance calls

# In-process cache: contract_address -> chain string
_chain_cache: dict[str, str] = {}


# ─────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────

def _fetch_json(url: str, params: dict = None) -> dict:
    """GET JSON from GMGN via curl_cffi Chrome impersonation with retry."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = cf_requests.get(
                url,
                params=params or {},
                headers=GMGN_HEADERS,
                impersonate="chrome120",
                timeout=15,
            )
            if resp.status_code == 429:
                wait = BACKOFF_BASE ** attempt
                print(f"[scraper] Rate limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                raise ScraperError("Access denied (403). IP may be Cloudflare-blocked.")
            resp.raise_for_status()
            return resp.json()
        except ScraperError:
            raise
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** attempt
                print(f"[scraper] Attempt {attempt}/{MAX_RETRIES} failed: {e}. Retry in {wait}s...",
                      file=sys.stderr)
                time.sleep(wait)
    raise ScraperError(f"All {MAX_RETRIES} attempts failed for {url}. Last: {last_error}")


def _evm_rpc_post(rpc_url: str, payload: dict) -> dict:
    """POST a JSON-RPC call to an EVM node. Returns {} on failure."""
    try:
        resp = cf_requests.post(
            rpc_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            impersonate="chrome120",
            timeout=10,
        )
        return resp.json()
    except Exception as e:
        print(f"[scraper] EVM RPC error ({rpc_url}): {e}", file=sys.stderr)
        return {}


def _sol_rpc_post(payload: dict) -> dict:
    """POST a JSON-RPC call to Solana mainnet. Returns {} on failure."""
    try:
        resp = cf_requests.post(
            config.CHAIN_CONFIG["sol"]["rpc_url"],
            json=payload,
            headers={"Content-Type": "application/json"},
            impersonate="chrome120",
            timeout=12,
        )
        return resp.json()
    except Exception as e:
        print(f"[scraper] Solana RPC error: {e}", file=sys.stderr)
        return {}


# ─────────────────────────────────────────────
# Chain detection
# ─────────────────────────────────────────────

def detect_chain(contract_address: str) -> str:
    """
    Auto-detect which chain a contract address belongs to.

    Logic:
      - Solana: base58 string, 32–44 chars, no '0x' prefix
      - EVM (eth/bsc/base): starts with '0x', exactly 42 chars
        → confirmed by calling eth_getCode on each chain RPC in order:
          eth → bsc → base. First chain returning non-'0x' bytecode wins.

    Results are cached in _chain_cache for the lifetime of the process.

    Returns:
        Chain string: "sol", "eth", "bsc", or "base"

    Raises:
        ScraperError: if address format is unrecognised or no chain has the contract.
    """
    if contract_address in _chain_cache:
        return _chain_cache[contract_address]

    # ── Solana address ───────────────────────────────────────────────
    import re
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", contract_address):
        _chain_cache[contract_address] = "sol"
        return "sol"

    # ── EVM address ──────────────────────────────────────────────────
    if re.match(r"^0x[0-9a-fA-F]{40}$", contract_address):
        for chain in config.EVM_DETECTION_ORDER:
            rpc_url = config.CHAIN_CONFIG[chain]["rpc_url"]
            print(f"[scraper] Probing {chain} for {contract_address[:10]}...", file=sys.stderr)
            result = _evm_rpc_post(rpc_url, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getCode",
                "params": [contract_address, "latest"],
            })
            code = result.get("result", "0x")
            # Non-trivial bytecode means the contract exists on this chain
            if code and code != "0x" and len(code) > 4:
                print(f"[scraper] Contract found on {chain}.", file=sys.stderr)
                _chain_cache[contract_address] = chain
                return chain
            time.sleep(0.3)  # brief pause between chain probes

        raise ScraperError(
            f"EVM address {contract_address} was not found on any supported chain "
            f"({', '.join(config.EVM_DETECTION_ORDER)}). "
            "Verify the contract address and try again."
        )

    raise ScraperError(
        f"Unrecognised address format: {contract_address!r}. "
        "Expected a Solana base58 address (32–44 chars) or EVM 0x address (42 chars)."
    )


# ─────────────────────────────────────────────
# Field extraction
# ─────────────────────────────────────────────

def _extract_trader(raw: dict, chain: str) -> dict:
    """
    Normalise a raw GMGN token_traders dict.

    Solana field verification (RPC getAccountInfo):
      "address"         → System Program owner = real wallet ✅
      "account_address" → Token-2022 owner     = SPL token account ❌

    EVM: "address" is always the wallet. "account_address" is empty string.

    native_balance in GMGN response:
      Solana: not present (fetched separately via RPC getBalance)
      EVM:    decimal string of wei (e.g. "12666555631944167") — converted to native token
    """
    if chain == "sol":
        wallet = raw.get("address") or "unknown"
        # Solana native_balance not in token_traders response — fetched via RPC later
        gmgn_native_balance = None
    else:
        # EVM: address IS the wallet directly; account_address is always empty
        wallet = raw.get("address") or "unknown"
        # GMGN provides decimal wei string in native_balance field — use it to skip RPC calls
        raw_nb = raw.get("native_balance") or "0"
        try:
            gmgn_native_balance = round(int(str(raw_nb)) / 1e18, 6)
        except (ValueError, TypeError):
            gmgn_native_balance = None  # fall back to RPC fetch

    pnl_usd             = float(raw.get("profit") or 0)
    realized_profit_usd = float(raw.get("realized_profit") or 0)
    buys                = int(raw.get("buy_tx_count_cur") or 0)
    sells               = int(raw.get("sell_tx_count_cur") or 0)

    return {
        "wallet_address":      wallet,
        "pnl_usd":             round(pnl_usd, 2),
        "realized_profit_usd": round(realized_profit_usd, 2),
        "win_rate_pct":        None,            # filled by win rate loop
        "native_balance":      gmgn_native_balance,  # pre-filled for EVM, None for Solana
        "tx_count":            buys + sells,
        "chain":               chain,
    }


# ─────────────────────────────────────────────
# Public: native balance
# ─────────────────────────────────────────────

def fetch_native_balance(wallet_address: str, chain: str) -> float:
    """
    Fetch current native token balance for a wallet.

    Solana → getBalance (lamports → SOL)
    EVM    → eth_getBalance (wei → native token)

    Returns balance as float. Returns 0.0 on any error.
    """
    try:
        chain_cfg = config.CHAIN_CONFIG[chain]

        if chain == "sol":
            result = _sol_rpc_post({
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [wallet_address],
            })
            lamports = (result.get("result") or {}).get("value", 0) or 0
            return round(lamports / 1_000_000_000, 6)

        else:  # EVM
            result = _evm_rpc_post(chain_cfg["rpc_url"], {
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_getBalance",
                "params": [wallet_address, "latest"],
            })
            hex_wei = result.get("result", "0x0") or "0x0"
            wei = int(hex_wei, 16)
            return round(wei / 1e18, 6)

    except Exception as e:
        print(f"[scraper] Balance fetch failed for {wallet_address[:8]}...: {e}", file=sys.stderr)
        return 0.0


# ─────────────────────────────────────────────
# Public: per-wallet win rate
# ─────────────────────────────────────────────

def fetch_wallet_winrate(wallet_address: str, chain: str,
                         period: str = WALLET_STAT_PERIOD) -> float:
    """
    Fetch real per-trade win rate % from GMGN wallet profit-stat endpoint.
    Returns 0.0 for non-indexed wallets. Never raises.
    """
    url = WALLET_STAT_URL.format(
        chain=config.CHAIN_CONFIG[chain]["gmgn_chain"],
        wallet_address=wallet_address,
        period=period,
    )
    try:
        data = _fetch_json(url)
        pnl_detail = (data.get("data") or {}).get("pnl_detail") or {}
        raw_wr = pnl_detail.get("winrate")
        if raw_wr is None or raw_wr == "" or str(raw_wr) == "0":
            return 0.0
        wr = float(raw_wr)
        return round(wr * 100, 2) if wr <= 1.0 else round(wr, 2)
    except Exception as e:
        print(f"[scraper] Win rate fetch failed for {wallet_address[:8]}...: {e}", file=sys.stderr)
        return 0.0


# ─────────────────────────────────────────────
# Public: top traders (full pipeline)
# ─────────────────────────────────────────────

def fetch_top_traders(contract_address: str, limit: int = 50) -> tuple[list[dict], str]:
    """
    Fetch top traders for a token from GMGN.ai, enriched with win rate
    and native balance. Chain is auto-detected.

    Returns:
        (traders, chain) — list of enriched trader dicts + detected chain string

    Each trader dict:
        wallet_address, pnl_usd, realized_profit_usd,
        win_rate_pct, native_balance, tx_count, chain

    Raises ScraperError on failure.
    """
    if not contract_address or len(contract_address) < 32:
        raise ScraperError(f"Invalid contract address: {contract_address!r}")

    # ── Step 1: detect chain ─────────────────────────────────────────
    chain = detect_chain(contract_address)
    gmgn_chain = config.CHAIN_CONFIG[chain]["gmgn_chain"]
    print(f"[scraper] Detected chain: {chain.upper()}", file=sys.stderr)

    # ── Step 2: fetch traders ────────────────────────────────────────
    data = _fetch_json(
        TOKEN_TRADERS_URL.format(chain=gmgn_chain, contract_address=contract_address),
        {"limit": limit, "orderby": "profit", "direction": "desc"},
    )

    if data.get("code") != 0:
        raise ScraperError(
            f"GMGN API error {data.get('code')}: "
            f"{data.get('message') or data.get('reason') or 'unknown'}"
        )

    raw_list = (data.get("data") or {}).get("list") or []
    if not raw_list:
        raise ScraperError(
            f"No trader data for {contract_address} on {chain.upper()}. "
            "Token may be too new, illiquid, or untracked by GMGN."
        )

    traders = [_extract_trader(r, chain) for r in raw_list]
    total = len(traders)

    # ── Step 3: win rates ────────────────────────────────────────────
    print(f"[scraper] Fetching win rates for {total} wallets (~{total}s)...", file=sys.stderr)
    for i, trader in enumerate(traders):
        wallet = trader["wallet_address"]
        wr = 0.0 if wallet == "unknown" else fetch_wallet_winrate(wallet, chain)
        trader["win_rate_pct"] = wr
        print(f"[scraper] [{i+1}/{total}] {wallet[:8]}... win_rate={wr:.1f}%", file=sys.stderr)
        if i < total - 1:
            time.sleep(WINRATE_FETCH_DELAY)

    # ── Step 4: native balances ──────────────────────────────────────
    # EVM: native_balance already extracted from GMGN decimal-wei field.
    # Solana: must be fetched via RPC (not present in token_traders response).
    native_sym  = config.CHAIN_CONFIG[chain]["native_symbol"]
    needs_rpc   = [t for t in traders if t["native_balance"] is None]
    if needs_rpc:
        print(f"[scraper] Fetching {native_sym} balances for {len(needs_rpc)} wallets via RPC...",
              file=sys.stderr)
        for i, trader in enumerate(needs_rpc):
            wallet = trader["wallet_address"]
            bal = 0.0 if wallet == "unknown" else fetch_native_balance(wallet, chain)
            trader["native_balance"] = bal
            print(f"[scraper] [{i+1}/{len(needs_rpc)}] {wallet[:8]}... {native_sym}={bal:.4f}",
                  file=sys.stderr)
            if i < len(needs_rpc) - 1:
                time.sleep(BALANCE_FETCH_DELAY)
    else:
        print(f"[scraper] {native_sym} balances pre-filled from GMGN (skipping RPC).",
              file=sys.stderr)

    # ── Step 5: sort ─────────────────────────────────────────────────
    traders.sort(key=lambda t: (t["win_rate_pct"] or 0, t["tx_count"]), reverse=True)

    return traders[:limit], chain


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _print_table(traders: list[dict], chain: str):
    if not traders:
        print("No traders found.")
        return
    native_sym = config.CHAIN_CONFIG.get(chain, {}).get("native_symbol", "BAL")
    W_RANK = 4; W_WALLET = 44; W_PNL = 16; W_REAL = 16; W_WR = 12; W_TX = 6; W_BAL = 12
    header = (
        f"{'#':<{W_RANK}} {'WALLET':<{W_WALLET}} "
        f"{'PnL (USD)':>{W_PNL}} {'REALIZED (USD)':>{W_REAL}} "
        f"{'WIN RATE %':>{W_WR}} {'TXs':>{W_TX}} {native_sym+' BAL':>{W_BAL}}"
    )
    sep = "─" * len(header)
    print(sep); print(header); print(sep)
    for i, t in enumerate(traders, 1):
        wr_str  = f"{t['win_rate_pct']:.1f}%" if t.get("win_rate_pct") else "N/A"
        bal_str = f"{t['native_balance']:.4f}" if t.get("native_balance") is not None else "N/A"
        pnl_str  = f"${t['pnl_usd']:+,.2f}"
        real_str = f"${t['realized_profit_usd']:+,.2f}"
        print(
            f"{str(i):<{W_RANK}} {t['wallet_address']:<{W_WALLET}} "
            f"{pnl_str:>{W_PNL}} {real_str:>{W_REAL}} "
            f"{wr_str:>{W_WR}} {str(t['tx_count']):>{W_TX}} {bal_str:>{W_BAL}}"
        )
    print(sep)
    print(f"  {len(traders)} traders | {chain.upper()} | win rate = 30d per-trade %")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <contract_address> [limit]")
        sys.exit(1)
    contract = sys.argv[1].strip()
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    print(f"[scraper] Fetching top {lim} traders for {contract}...", file=sys.stderr)
    try:
        results, detected_chain = fetch_top_traders(contract, limit=lim)
        _print_table(results, detected_chain)
    except ScraperError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
