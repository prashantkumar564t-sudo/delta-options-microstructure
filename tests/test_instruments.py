"""
tests/test_instruments.py
Unit tests for instrument parsing, expiry classification, delta banding, spot tracking, and quote tracking.
"""

import unittest
from datetime import date, datetime, time, timezone
from src.instruments import (
    QuoteTracker,
    SpotTracker,
    classify_delta_band,
    classify_expiry_bucket,
    discover_options_microstructure,
    parse_expiry_date,
)


class TestInstruments(unittest.TestCase):
    """Test suite for instrument classification and microstructure formulas."""

    def test_parse_expiry_date(self):
        self.assertEqual(parse_expiry_date("C-BTC-95000-141126"), date(2026, 11, 14))
        self.assertEqual(parse_expiry_date("P-ETH-2800-290127"), date(2027, 1, 29))
        self.assertEqual(parse_expiry_date("C-XAUT-3800-051226"), date(2026, 12, 5))
        self.assertIsNone(parse_expiry_date("BTCUSD"))
        self.assertIsNone(parse_expiry_date("INVALID-OPTION"))
        self.assertIsNone(parse_expiry_date("C-BTC-95000-ABCDEF"))

    def test_classify_expiry_bucket(self):
        # 14 Nov 2026 at 10:00 UTC (before 12:00 UTC settlement)
        ref_utc = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

        # 0-DTE (today 14 Nov)
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 14), current_utc=ref_utc), "0-DTE")
        # 1-DTE (tomorrow 15 Nov)
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 15), current_utc=ref_utc), "1-DTE")
        # 2-DTE (16 Nov)
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 16), current_utc=ref_utc), "2-DTE")
        # WEEKLY (3 to 21 days: e.g. 21 Nov -> 7 days, 28 Nov -> 14 days)
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 21), current_utc=ref_utc), "WEEKLY")
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 28), current_utc=ref_utc), "WEEKLY")
        self.assertEqual(classify_expiry_bucket(date(2026, 12, 5), current_utc=ref_utc), "WEEKLY")
        # MONTHLY (> 21 days: e.g. 25 Dec -> 41 days)
        self.assertEqual(classify_expiry_bucket(date(2026, 12, 25), current_utc=ref_utc), "MONTHLY")
        # Expired (yesterday 13 Nov)
        self.assertIsNone(classify_expiry_bucket(date(2026, 11, 13), current_utc=ref_utc))

    def test_classify_expiry_bucket_after_settlement(self):
        # 14 Nov 2026 at 13:00 UTC (after 12:00 UTC settlement)
        ref_utc = datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc)

        # 14 Nov has passed settlement
        self.assertIsNone(classify_expiry_bucket(date(2026, 11, 14), current_utc=ref_utc))
        # 15 Nov is now 0-DTE
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 15), current_utc=ref_utc), "0-DTE")
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 16), current_utc=ref_utc), "1-DTE")
        self.assertEqual(classify_expiry_bucket(date(2026, 11, 17), current_utc=ref_utc), "2-DTE")

    def test_classify_delta_band(self):
        self.assertEqual(classify_delta_band(0.04), "FAR_OTM_<0.07")
        self.assertEqual(classify_delta_band(-0.06), "FAR_OTM_<0.07")
        self.assertEqual(classify_delta_band(0.09), "0.07-0.11")
        self.assertEqual(classify_delta_band(-0.105), "0.07-0.11")
        self.assertEqual(classify_delta_band(0.12), "0.11-0.14")
        self.assertEqual(classify_delta_band(-0.139), "0.11-0.14")
        self.assertEqual(classify_delta_band(0.15), "0.14-0.18")
        self.assertEqual(classify_delta_band(-0.179), "0.14-0.18")
        self.assertEqual(classify_delta_band(0.22), "0.18-0.25")
        self.assertEqual(classify_delta_band(-0.245), "0.18-0.25")
        self.assertEqual(classify_delta_band(0.45), "ATM_0.25-0.55")
        self.assertEqual(classify_delta_band(-0.50), "ATM_0.25-0.55")
        self.assertEqual(classify_delta_band(0.85), "ITM_>0.55")
        self.assertEqual(classify_delta_band(-0.95), "ITM_>0.55")
        self.assertEqual(classify_delta_band(None), "UNKNOWN")

    def test_spot_tracker(self):
        tracker = SpotTracker(window_seconds=60)
        # Initial point
        c1 = tracker.update("BTC", 90000.0, current_time=100.0)
        self.assertAlmostEqual(c1, 0.0)

        # 30 seconds later, spot up by 1%
        c2 = tracker.update("BTC", 90900.0, current_time=130.0)
        self.assertAlmostEqual(c2, 1.0)

        # 70 seconds later (> 60s from start), spot down to 89991 vs point at t=130
        c3 = tracker.update("BTC", 89991.0, current_time=170.0)
        # Point at t=100 is evicted (cutoff = 170 - 60 = 110; t=100 < 110)
        # Comparison is against t=130 (90900.0): (89991 - 90900) / 90900 * 100 = -1.0%
        self.assertAlmostEqual(c3, -1.0)

    def test_quote_tracker(self):
        tracker = QuoteTracker()
        # First observation -> 1 (new quote)
        self.assertEqual(tracker.check_and_update("C-BTC-95000-141126", 100.0, 110.0), 1)
        # Same observation -> 0 (static quote)
        self.assertEqual(tracker.check_and_update("C-BTC-95000-141126", 100.0, 110.0), 0)
        # Bid changed -> 1 (updated quote)
        self.assertEqual(tracker.check_and_update("C-BTC-95000-141126", 101.0, 110.0), 1)
        # Ask changed -> 1 (updated quote)
        self.assertEqual(tracker.check_and_update("C-BTC-95000-141126", 101.0, 109.0), 1)

    def test_discover_options_microstructure(self):
        ref_utc = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
        mock_tickers = [
            # Underlying spot perpetual
            {
                "symbol": "BTCUSD",
                "contract_type": "perpetual_futures",
                "spot_price": "92000.0",
                "close": "92000.0"
            },
            # Active OTM Call
            {
                "symbol": "C-BTC-95000-141126",
                "contract_type": "call_options",
                "underlying_asset_symbol": "BTC",
                "strike_price": "95000",
                "mark_price": "100.0",
                "close": "98.0",
                "quotes": {
                    "best_bid": "95.0",
                    "best_ask": "105.0",
                    "bid_size": "500",
                    "ask_size": "600",
                    "mark_iv": "0.55"
                },
                "greeks": {"delta": "0.12"},
                "volume_24h": "150000",
                "open_interest": "1250"
            },
            # Inactive option (no bid & no ask) -> should be filtered
            {
                "symbol": "P-BTC-50000-141126",
                "contract_type": "put_options",
                "underlying_asset_symbol": "BTC",
                "strike_price": "50000",
                "mark_price": "1.0",
                "quotes": {"best_bid": "0.0", "best_ask": "0.0"},
                "greeks": {"delta": "-0.01"}
            },
            # Gold option (XAUT alias)
            {
                "symbol": "P-XAUT-3800-151126",
                "contract_type": "put_options",
                "underlying_asset_symbol": "XAUT",
                "strike_price": "3800",
                "mark_price": "10.0",
                "close": "10.5",
                "quotes": {"best_bid": "9.5", "best_ask": "10.5", "bid_size": "200", "ask_size": "250"},
                "greeks": {"delta": "-0.15"}
            }
        ]

        spot_tracker = SpotTracker()
        quote_tracker = QuoteTracker()

        records = discover_options_microstructure(
            tickers=mock_tickers,
            spot_tracker=spot_tracker,
            quote_tracker=quote_tracker,
            underlyings=("BTC", "XAUT"),
            current_utc=ref_utc,
            require_active_orderbook=True,
        )

        # Inactive P-BTC-50000-141126 should be omitted
        self.assertEqual(len(records), 2)

        btc_opt = next(r for r in records if r["symbol"] == "C-BTC-95000-141126")
        self.assertEqual(btc_opt["underlying"], "BTC")
        self.assertEqual(btc_opt["expiry_bucket"], "0-DTE")
        self.assertEqual(btc_opt["option_type"], "CE")
        self.assertEqual(btc_opt["delta_band"], "0.11-0.14")
        self.assertAlmostEqual(btc_opt["spot_price"], 92000.0)
        self.assertAlmostEqual(btc_opt["mark_price"], 100.0)
        # spread_vs_mark_pct = (105 - 95) / 100 * 100 = 10.0%
        self.assertAlmostEqual(btc_opt["spread_vs_mark_pct"], 10.0)
        # bid_slippage_pct = (100 - 95) / 100 * 100 = 5.0%
        self.assertAlmostEqual(btc_opt["bid_slippage_pct"], 5.0)
        # ltp_mark_spike_pct = (98 - 100) / 100 * 100 = -2.0%
        self.assertAlmostEqual(btc_opt["ltp_mark_spike_pct"], -2.0)
        self.assertEqual(btc_opt["quote_changed"], 1)

        gold_opt = next(r for r in records if r["symbol"] == "P-XAUT-3800-151126")
        self.assertEqual(gold_opt["underlying"], "XAUT")
        self.assertEqual(gold_opt["expiry_bucket"], "1-DTE")
        self.assertEqual(gold_opt["delta_band"], "0.14-0.18")
        self.assertAlmostEqual(gold_opt["bid_slippage_pct"], 5.0)


if __name__ == "__main__":
    unittest.main()
