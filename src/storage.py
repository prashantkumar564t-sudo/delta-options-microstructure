"""
src/storage.py
High-throughput, lossless SQLite WAL telemetry storage sink for options microstructure.
Zero-dependency Python 3 Standard Library.
"""

import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from src import config


class OptionsMicrostructureStorage:
    """High-performance SQLite WAL storage sink with buffering and low memory footprint."""

    def __init__(self, db_path: Optional[Path] = None, batch_size: int = config.BATCH_SIZE):
        self.db_path = Path(db_path or config.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.batch_size = max(1, batch_size)
        self._buffer: List[tuple] = []

        self._conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self):
        """Configure SQLite pragmas (WAL, NORMAL sync, MEMORY temp store) and idempotent schema."""
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode = WAL;")
        cur.execute("PRAGMA synchronous = NORMAL;")
        cur.execute("PRAGMA temp_store = MEMORY;")
        cur.execute("PRAGMA cache_size = -2000;")  # 2 MB cache to preserve < 30 MB memory limit

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS options_microstructure (
                timestamp_us INTEGER NOT NULL,
                datetime_ist TEXT NOT NULL,
                underlying TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                expiry_bucket TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike REAL NOT NULL,
                delta REAL,
                delta_band TEXT NOT NULL,
                iv REAL,
                spot_price REAL NOT NULL,
                spot_1m_change_pct REAL NOT NULL,
                mark_price REAL NOT NULL,
                ltp REAL,
                best_bid REAL NOT NULL,
                best_ask REAL NOT NULL,
                bid_size REAL NOT NULL,
                ask_size REAL NOT NULL,
                volume_24h REAL NOT NULL,
                oi REAL NOT NULL,
                spread_vs_mark_pct REAL NOT NULL,
                bid_slippage_pct REAL NOT NULL,
                ltp_mark_spike_pct REAL NOT NULL,
                quote_changed INTEGER NOT NULL,
                PRIMARY KEY (symbol, timestamp_us)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_opt_micro_ts ON options_microstructure (timestamp_us);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_opt_micro_und_exp ON options_microstructure (underlying, expiry_bucket, delta_band);"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_opt_micro_quote ON options_microstructure (quote_changed);")
        self._conn.commit()

    def write_records(self, records: List[dict]):
        """Buffer enriched options microstructure records for batched SQLite commit."""
        if not records:
            return

        for r in records:
            row = (
                int(r["timestamp_us"]),
                str(r["datetime_ist"]),
                str(r["underlying"]),
                str(r["symbol"]),
                str(r["expiry_date"]),
                str(r["expiry_bucket"]),
                str(r["option_type"]),
                float(r["strike"]),
                float(r["delta"]) if r.get("delta") is not None else None,
                str(r["delta_band"]),
                float(r["iv"]) if r.get("iv") is not None else None,
                float(r.get("spot_price", 0.0)),
                float(r.get("spot_1m_change_pct", 0.0)),
                float(r.get("mark_price", 0.0)),
                float(r["ltp"]) if r.get("ltp") is not None else None,
                float(r.get("best_bid", 0.0)),
                float(r.get("best_ask", 0.0)),
                float(r.get("bid_size", 0.0)),
                float(r.get("ask_size", 0.0)),
                float(r.get("volume_24h", 0.0)),
                float(r.get("oi", 0.0)),
                float(r.get("spread_vs_mark_pct", 0.0)),
                float(r.get("bid_slippage_pct", 0.0)),
                float(r.get("ltp_mark_spike_pct", 0.0)),
                int(r.get("quote_changed", 1)),
            )
            self._buffer.append(row)

        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        """Execute batched executemany insert with transaction commit."""
        if not self._buffer:
            return

        cur = self._conn.cursor()
        cur.executemany(
            """
            INSERT OR IGNORE INTO options_microstructure (
                timestamp_us, datetime_ist, underlying, symbol, expiry_date,
                expiry_bucket, option_type, strike, delta, delta_band,
                iv, spot_price, spot_1m_change_pct, mark_price, ltp,
                best_bid, best_ask, bid_size, ask_size, volume_24h, oi,
                spread_vs_mark_pct, bid_slippage_pct, ltp_mark_spike_pct,
                quote_changed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            self._buffer,
        )
        self._conn.commit()
        self._buffer.clear()

    def close(self):
        """Flush buffer and safely close SQLite connection."""
        self.flush()
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
