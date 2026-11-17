"""
src/instruments.py
Dynamic options discovery, all-expiry classification, delta-band tagging, and microstructure formulas.
Zero-dependency Python 3 Standard Library.
"""

from collections import deque
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from src import config


def parse_expiry_date(symbol: str) -> Optional[date]:
    """
    Extract expiry date from option symbol.
    Format: {C|P}-{UNDERLYING}-{STRIKE}-{DDMMYY}
    e.g. C-BTC-99000-141126 -> date(2026, 11, 14)
    """
    parts = symbol.split("-")
    if len(parts) < 4:
        return None
    date_str = parts[-1]
    if len(date_str) != 6 or not date_str.isdigit():
        return None
    try:
        day = int(date_str[0:2])
        month = int(date_str[2:4])
        year = 2000 + int(date_str[4:6])
        return date(year, month, day)
    except ValueError:
        return None


def classify_expiry_bucket(
    expiry_date: date,
    current_utc: Optional[datetime] = None
) -> Optional[str]:
    """
    Classify option expiry into:
    - 0-DTE: Next settlement (<24h)
    - 1-DTE: +1 Day
    - 2-DTE: +2 Days
    - WEEKLY: 3 to 21 Days
    - MONTHLY: > 21 Days
    Returns None if already settled/expired.
    """
    now = current_utc or datetime.now(timezone.utc)
    settlement_dt = datetime.combine(
        expiry_date,
        time(config.DELTA_SETTLEMENT_HOUR_UTC, 0, tzinfo=timezone.utc)
    )

    if settlement_dt <= now:
        return None

    # Target settlement date for 0-DTE
    if now.time() < time(config.DELTA_SETTLEMENT_HOUR_UTC, 0):
        d0 = now.date()
    else:
        d0 = now.date() + timedelta(days=1)

    delta_days = (expiry_date - d0).days
    if delta_days < 0:
        return None
    elif delta_days == 0:
        return "0-DTE"
    elif delta_days == 1:
        return "1-DTE"
    elif delta_days == 2:
        return "2-DTE"
    elif 3 <= delta_days <= 21:
        return "WEEKLY"
    else:
        return "MONTHLY"


def classify_delta_band(delta: Optional[float]) -> str:
    """
    Tag options into discrete delta bands:
    - FAR_OTM_<0.07
    - 0.07-0.11
    - 0.11-0.14
    - 0.14-0.18
    - 0.18-0.25
    - ATM_0.25-0.55
    - ITM_>0.55
    """
    if delta is None:
        return "UNKNOWN"
    abs_d = abs(float(delta))
    if abs_d < 0.07:
        return "FAR_OTM_<0.07"
    elif abs_d < 0.11:
        return "0.07-0.11"
    elif abs_d < 0.14:
        return "0.11-0.14"
    elif abs_d < 0.18:
        return "0.14-0.18"
    elif abs_d < 0.25:
        return "0.18-0.25"
    elif abs_d <= 0.55:
        return "ATM_0.25-0.55"
    else:
        return "ITM_>0.55"


class SpotTracker:
    """High-precision in-memory rolling sliding buffer for underlying spot 1m change pct."""

    def __init__(self, window_seconds: int = config.SPOT_BUFFER_WINDOW_SEC):
        self.window_seconds = window_seconds
        # underlying -> deque of (timestamp_monotonic, spot_price)
        self._buffers: Dict[str, deque] = {}

    def update(self, underlying: str, spot_price: float, current_time: Optional[float] = None) -> float:
        """Record spot and return spot_1m_change_pct = (spot_now - spot_60s_ago) / spot_60s_ago * 100."""
        now = current_time if current_time is not None else datetime.now(timezone.utc).timestamp()
        if underlying not in self._buffers:
            self._buffers[underlying] = deque()

        buf = self._buffers[underlying]
        buf.append((now, float(spot_price)))

        # Evict records older than window
        cutoff = now - self.window_seconds
        while len(buf) > 1 and buf[0][0] < cutoff:
            buf.popleft()

        oldest_spot = buf[0][1]
        if oldest_spot > 0:
            return ((spot_price - oldest_spot) / oldest_spot) * 100.0
        return 0.0


class QuoteTracker:
    """In-memory cache of previous (best_bid, best_ask) per contract to detect quote changes."""

    def __init__(self):
        self._cache: Dict[str, Tuple[float, float]] = {}

    def check_and_update(self, symbol: str, best_bid: float, best_ask: float) -> int:
        """Returns 1 if quotes changed since last observation (or first seen), 0 if static."""
        current = (float(best_bid), float(best_ask))
        if symbol not in self._cache:
            self._cache[symbol] = current
            return 1

        prev = self._cache[symbol]
        if current != prev:
            self._cache[symbol] = current
            return 1
        return 0


def discover_options_microstructure(
    tickers: List[dict],
    spot_tracker: Optional[SpotTracker] = None,
    quote_tracker: Optional[QuoteTracker] = None,
    underlyings: Tuple[str, ...] = config.TARGET_UNDERLYINGS,
    current_utc: Optional[datetime] = None,
    require_active_orderbook: bool = True,
) -> List[dict]:
    """
    Scan all active market tickers, classify expiries and delta bands,
    compute microstructure metrics, and return structured telemetry records.
    """
    now_utc = current_utc or datetime.now(timezone.utc)
    ist_dt = now_utc.astimezone(config.IST)
    datetime_ist = ist_dt.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_us = int(now_utc.timestamp() * 1_000_000)

    target_set = {u.strip().upper() for u in underlyings if u.strip()}
    if any(g in target_set for g in ("PAXG", "XAUT", "GOLD")):
        target_set.update({"PAXG", "XAUT", "GOLD"})

    # 1. First pass: extract spot prices for underlyings from perpetuals or spot tickers
    spots: Dict[str, float] = {}
    for t in tickers:
        ctype = t.get("contract_type", "")
        sym = t.get("symbol", "")
        if ctype == "perpetual_futures" or "USD" in sym:
            for u in ("BTC", "ETH", "XAUT", "PAXG"):
                if sym.startswith(u) or t.get("underlying_asset_symbol") == u:
                    raw_sp = t.get("spot_price") or t.get("mark_price") or t.get("close")
                    if raw_sp:
                        spots[u] = float(raw_sp)
                        if u in ("PAXG", "XAUT"):
                            spots["GOLD"] = float(raw_sp)
                            spots["PAXG"] = float(raw_sp)
                            spots["XAUT"] = float(raw_sp)

    # 2. Second pass: scan options
    results = []

    for t in tickers:
        ctype = t.get("contract_type", "")
        sym = t.get("symbol", "")

        if ctype not in ("call_options", "put_options") and not (sym.startswith("C-") or sym.startswith("P-")):
            continue

        u_raw = (t.get("underlying_asset_symbol") or "").upper()
        matched_u = None
        if u_raw in target_set:
            matched_u = u_raw
        else:
            for u in target_set:
                if f"-{u}-" in sym:
                    matched_u = u
                    break

        if not matched_u:
            continue

        # Parse expiry date
        exp_d = parse_expiry_date(sym)
        if not exp_d:
            continue

        expiry_bucket = classify_expiry_bucket(exp_d, current_utc=now_utc)
        if not expiry_bucket:
            continue  # Expired or past settlement

        quotes = t.get("quotes") or {}

        # Best Bid and Best Ask
        try:
            best_bid = float(quotes.get("best_bid")) if quotes.get("best_bid") not in (None, "") else 0.0
        except (ValueError, TypeError):
            best_bid = 0.0

        try:
            best_ask = float(quotes.get("best_ask")) if quotes.get("best_ask") not in (None, "") else 0.0
        except (ValueError, TypeError):
            best_ask = 0.0

        # Filter active orderbook if requested (best_bid > 0 or best_ask > 0)
        if require_active_orderbook and best_bid <= 0.0 and best_ask <= 0.0:
            continue

        # Option type
        if ctype == "call_options" or sym.startswith("C-"):
            option_type = "CE"
        elif ctype == "put_options" or sym.startswith("P-"):
            option_type = "PE"
        else:
            option_type = "UNKNOWN"

        # Strike price
        try:
            strike = float(t.get("strike_price") or 0.0)
        except (ValueError, TypeError):
            strike = 0.0

        # Greeks & Delta
        greeks = t.get("greeks") or {}
        delta_raw = greeks.get("delta")
        try:
            delta = float(delta_raw) if delta_raw is not None else None
        except (ValueError, TypeError):
            delta = None

        delta_band = classify_delta_band(delta)

        # Mark Price
        try:
            mark_price = float(t.get("mark_price") or 0.0)
        except (ValueError, TypeError):
            mark_price = 0.0

        # LTP (close or last_price)
        close_raw = t.get("close") or t.get("last_price")
        try:
            ltp = float(close_raw) if close_raw not in (None, "") else None
        except (ValueError, TypeError):
            ltp = None

        # Bid Size & Ask Size
        try:
            bid_size = float(quotes.get("bid_size") or 0.0)
        except (ValueError, TypeError):
            bid_size = 0.0

        try:
            ask_size = float(quotes.get("ask_size") or 0.0)
        except (ValueError, TypeError):
            ask_size = 0.0

        # Implied Volatility
        iv_raw = quotes.get("mark_iv") or t.get("mark_iv") or quotes.get("ask_iv") or quotes.get("bid_iv")
        try:
            iv = float(iv_raw) if iv_raw not in (None, "") else None
        except (ValueError, TypeError):
            iv = None

        # Volume 24h & Open Interest
        try:
            volume_24h = float(t.get("volume_24h") or t.get("volume") or 0.0)
        except (ValueError, TypeError):
            volume_24h = 0.0

        try:
            oi = float(t.get("open_interest") or t.get("oi") or 0.0)
        except (ValueError, TypeError):
            oi = 0.0

        # Underlying Spot Price & 1m Change
        spot_price = spots.get(matched_u, 0.0)
        spot_1m_change_pct = 0.0
        if spot_tracker and spot_price > 0.0:
            spot_1m_change_pct = spot_tracker.update(
                matched_u, spot_price, current_time=now_utc.timestamp()
            )

        # Microstructure Formulas
        if mark_price > 0.0:
            spread_vs_mark_pct = ((best_ask - best_bid) / mark_price) * 100.0
            bid_slippage_pct = ((mark_price - best_bid) / mark_price) * 100.0
            ltp_mark_spike_pct = (((ltp - mark_price) / mark_price) * 100.0) if ltp is not None else 0.0
        else:
            spread_vs_mark_pct = 0.0
            bid_slippage_pct = 0.0
            ltp_mark_spike_pct = 0.0

        # Quote changed indicator
        quote_changed = 1
        if quote_tracker:
            quote_changed = quote_tracker.check_and_update(sym, best_bid, best_ask)

        record = {
            "timestamp_us": timestamp_us,
            "datetime_ist": datetime_ist,
            "underlying": matched_u,
            "symbol": sym,
            "expiry_date": exp_d.isoformat(),
            "expiry_bucket": expiry_bucket,
            "option_type": option_type,
            "strike": strike,
            "delta": delta,
            "delta_band": delta_band,
            "iv": iv,
            "spot_price": spot_price,
            "spot_1m_change_pct": spot_1m_change_pct,
            "mark_price": mark_price,
            "ltp": ltp,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "volume_24h": volume_24h,
            "oi": oi,
            "spread_vs_mark_pct": spread_vs_mark_pct,
            "bid_slippage_pct": bid_slippage_pct,
            "ltp_mark_spike_pct": ltp_mark_spike_pct,
            "quote_changed": quote_changed,
        }
        results.append(record)

    return results
