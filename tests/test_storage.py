"""
tests/test_storage.py
Unit tests for SQLite WAL options microstructure telemetry persistence.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage import OptionsMicrostructureStorage


class TestStorage(unittest.TestCase):
    """Test suite for SQLite WAL storage sink."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_microstructure.db"
        self.storage = OptionsMicrostructureStorage(db_path=self.db_path, batch_size=2)

    def tearDown(self):
        if self.storage:
            self.storage.close()
        self.temp_dir.cleanup()

    def test_pragmas(self):
        cur = self.storage._conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        self.assertEqual(cur.fetchone()[0].lower(), "wal")
        cur.execute("PRAGMA synchronous;")
        self.assertEqual(cur.fetchone()[0], 1)  # NORMAL sync

    def test_write_and_flush(self):
        records = [
            {
                "timestamp_us": 1731575000000001,
                "datetime_ist": "2026-11-14 15:30:00",
                "underlying": "BTC",
                "symbol": "C-BTC-95000-141126",
                "expiry_date": "2026-11-14",
                "expiry_bucket": "0-DTE",
                "option_type": "CE",
                "strike": 95000.0,
                "delta": 0.12,
                "delta_band": "0.11-0.14",
                "iv": 0.55,
                "spot_price": 92000.0,
                "spot_1m_change_pct": 0.15,
                "mark_price": 100.0,
                "ltp": 98.0,
                "best_bid": 95.0,
                "best_ask": 105.0,
                "bid_size": 500.0,
                "ask_size": 600.0,
                "volume_24h": 150000.0,
                "oi": 1250.0,
                "spread_vs_mark_pct": 10.0,
                "bid_slippage_pct": 5.0,
                "ltp_mark_spike_pct": -2.0,
                "quote_changed": 1,
            },
            {
                "timestamp_us": 1731575000000002,
                "datetime_ist": "2026-11-14 15:30:00",
                "underlying": "ETH",
                "symbol": "P-ETH-2800-151126",
                "expiry_date": "2026-11-15",
                "expiry_bucket": "1-DTE",
                "option_type": "PE",
                "strike": 2800.0,
                "delta": -0.18,
                "delta_band": "0.14-0.18",
                "iv": 0.62,
                "spot_price": 3100.0,
                "spot_1m_change_pct": -0.10,
                "mark_price": 25.0,
                "ltp": 24.5,
                "best_bid": 23.0,
                "best_ask": 27.0,
                "bid_size": 400.0,
                "ask_size": 450.0,
                "volume_24h": 85000.0,
                "oi": 3400.0,
                "spread_vs_mark_pct": 16.0,
                "bid_slippage_pct": 8.0,
                "ltp_mark_spike_pct": -2.0,
                "quote_changed": 0,
            },
        ]

        self.storage.write_records(records)
        self.storage.flush()

        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM options_microstructure;")
        self.assertEqual(cur.fetchone()[0], 2)

        cur.execute(
            """
            SELECT underlying, expiry_bucket, delta_band, spread_vs_mark_pct, bid_slippage_pct, quote_changed
            FROM options_microstructure WHERE symbol = 'C-BTC-95000-141126';
            """
        )
        row = cur.fetchone()
        self.assertEqual(row[0], "BTC")
        self.assertEqual(row[1], "0-DTE")
        self.assertEqual(row[2], "0.11-0.14")
        self.assertAlmostEqual(row[3], 10.0)
        self.assertAlmostEqual(row[4], 5.0)
        self.assertEqual(row[5], 1)

        conn.close()


if __name__ == "__main__":
    unittest.main()
