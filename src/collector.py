"""
src/collector.py
Continuous high-frequency options microstructure telemetry collector.
Strictly zero-dependency Python 3 standard library.
"""

import gc
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from src import config
from src.delta_api import DeltaAPI
from src.instruments import (
    QuoteTracker,
    SpotTracker,
    discover_options_microstructure,
)
from src.storage import OptionsMicrostructureStorage


def trim_process_memory():
    """Trim unused pages from working set to maintain strict < 30 MB RAM ceiling."""
    gc.collect()
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            ctypes.windll.psapi.EmptyWorkingSet.restype = wintypes.BOOL
            ctypes.windll.psapi.EmptyWorkingSet(handle)
        except Exception:
            pass


def run_microstructure_collector(
    duration: int = 300,
    interval: float = config.DEFAULT_POLL_INTERVAL,
    underlyings: Tuple[str, ...] = config.TARGET_UNDERLYINGS,
    db_path: Optional[Path] = None,
    verbose: bool = True,
) -> dict:
    """
    Execute high-frequency options microstructure collection loop.
    Returns session metrics: {total_scans, total_records, errors, start_us, end_us}.
    """
    api = DeltaAPI(base_url=config.DELTA_BASE_URL, timeout=config.API_TIMEOUT)
    storage = OptionsMicrostructureStorage(db_path=db_path)
    spot_tracker = SpotTracker(window_seconds=config.SPOT_BUFFER_WINDOW_SEC)
    quote_tracker = QuoteTracker()

    scan_count = 0
    total_records = 0
    errors_count = 0
    start_us = int(time.time() * 1_000_000)

    if verbose:
        print("=" * 80)
        print("Delta Options Microstructure Telemetry Collector")
        print(f"Target Underlyings: {', '.join(underlyings)} | Polling: {interval}s | Duration: {duration}s")
        print(f"Database: {storage.db_path} (SQLite WAL)")
        print("=" * 80)

    trim_process_memory()
    start_time = time.monotonic()

    try:
        while True:
            elapsed = time.monotonic() - start_time
            if duration > 0 and elapsed >= duration:
                if verbose:
                    print("\n[+] Target collection duration elapsed.")
                break

            loop_start = time.monotonic()

            try:
                tickers = api.fetch_tickers()
                records = discover_options_microstructure(
                    tickers=tickers,
                    spot_tracker=spot_tracker,
                    quote_tracker=quote_tracker,
                    underlyings=underlyings,
                    require_active_orderbook=True,
                )

                if records:
                    storage.write_records(records)
                    storage.flush()

                scan_count += 1
                total_records += len(records)

                # Quick live stats
                quote_updates = sum(1 for r in records if r["quote_changed"] == 1)
                avg_slip = (sum(r["bid_slippage_pct"] for r in records) / len(records)) if records else 0.0

                if verbose:
                    dur_display = f"{duration}s" if duration > 0 else "∞"
                    status = (
                        f"\r[{scan_count:04d} | {int(elapsed):3d}s/{dur_display}] "
                        f"Active Options: {len(records):3d} | Quote Chg: {quote_updates:3d} | "
                        f"Avg Bid Slip: {avg_slip:5.2f}% | RTT: {api.last_rtt_ms:4.1f}ms"
                    )
                    sys.stdout.write(status)
                    sys.stdout.flush()

            except Exception as err:
                errors_count += 1
                if verbose:
                    print(f"\n[!] Snapshot warning: {err}")

            iteration_time = time.monotonic() - loop_start
            sleep_time = max(0.0, interval - iteration_time)
            trim_process_memory()
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        if verbose:
            print("\n[!] Collector stopped by user.")
    finally:
        storage.close()

    end_us = int(time.time() * 1_000_000)

    if verbose:
        print("\n" + "=" * 80)
        print("Options Microstructure Collection Complete!")
        print(f"Total Scans: {scan_count} | Records Logged: {total_records} | Errors: {errors_count}")
        print("=" * 80)

    return {
        "total_scans": scan_count,
        "total_records": total_records,
        "errors": errors_count,
        "start_us": start_us,
        "end_us": end_us,
        "db_path": str(storage.db_path),
    }
