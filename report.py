"""
report.py
Analytical reporting tool for Delta Options Microstructure database.
Outputs clean markdown / ASCII summary tables grouped by underlying, expiry, and delta band.
Zero-dependency Python 3 standard library.
"""

import argparse
import sqlite3
from pathlib import Path
from typing import Optional

from src import config


def generate_report(
    db_path: Optional[Path] = None,
    since_timestamp_us: Optional[int] = None,
    underlying: Optional[str] = None,
):
    """Query options_microstructure database and print rich tabular microstructure breakdown."""
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        print(f"[!] Database file not found at: {path}")
        return

    conn = sqlite3.connect(str(path))
    cur = conn.cursor()

    conditions = []
    params = []
    if since_timestamp_us:
        conditions.append("timestamp_us >= ?")
        params.append(since_timestamp_us)
    if underlying:
        conditions.append("underlying = ?")
        params.append(underlying.upper())

    where_str = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # 1. Total statistics
    cur.execute(f"SELECT count(*), count(distinct symbol), min(datetime_ist), max(datetime_ist) FROM options_microstructure {where_str};", params)
    total_rows, total_symbols, min_ist, max_ist = cur.fetchone()

    if not total_rows:
        print("[*] No records found matching criteria.")
        conn.close()
        return

    print("\n" + "=" * 125)
    print("DELTA OPTIONS MICROSTRUCTURE ANALYTICAL REPORT")
    print("=" * 125)
    print(f"Database Path  : {path}")
    print(f"Total Snapshots: {total_rows:,} records across {total_symbols} unique option contracts")
    print(f"Time Range IST : {min_ist} -> {max_ist}")
    print("=" * 125)

    # 2. Grouped breakdown: underlying, expiry_bucket, delta_band
    group_query = f"""
    SELECT 
        underlying,
        expiry_bucket,
        delta_band,
        count(*) as samples,
        avg(mark_price) as avg_mark,
        avg(best_bid) as avg_bid,
        avg(best_ask) as avg_ask,
        avg(bid_size) as avg_bid_size,
        avg(bid_slippage_pct) as avg_bid_slip_pct,
        avg(spread_vs_mark_pct) as avg_spr_pct,
        avg(quote_changed) * 100.0 as quote_churn_pct
    FROM options_microstructure
    {where_str}
    GROUP BY underlying, expiry_bucket, delta_band
    ORDER BY 
        underlying,
        CASE expiry_bucket 
            WHEN '0-DTE' THEN 1 
            WHEN '1-DTE' THEN 2 
            WHEN '2-DTE' THEN 3 
            WHEN 'WEEKLY' THEN 4 
            ELSE 5 
        END,
        CASE delta_band
            WHEN 'FAR_OTM_<0.07' THEN 1
            WHEN '0.07-0.11' THEN 2
            WHEN '0.11-0.14' THEN 3
            WHEN '0.14-0.18' THEN 4
            WHEN '0.18-0.25' THEN 5
            WHEN 'ATM_0.25-0.55' THEN 6
            ELSE 7
        END;
    """

    cur.execute(group_query, params)
    rows = cur.fetchall()

    header = (
        f"{'Underlying':<10} | {'Expiry':<8} | {'Delta Band':<14} | {'Samples':<7} | "
        f"{'Avg Mark':<11} | {'Avg Bid':<11} | {'Avg Ask':<11} | {'Avg Bid Size':<12} | "
        f"{'Bid Slip %':<10} | {'Spr/Mark %':<10} | {'Quote Churn':<11}"
    )
    print(header)
    print("-" * 125)

    for r in rows:
        u, exp, band, cnt, mark_p, b_bid, b_ask, b_size, slip_pct, spr_pct, churn = r
        print(
            f"{u:<10} | {exp:<8} | {band:<14} | {cnt:<7} | "
            f"${mark_p:>9.2f} | ${b_bid:>9.2f} | ${b_ask:>9.2f} | {b_size:>12.1f} | "
            f"{slip_pct:>9.2f}% | {spr_pct:>9.2f}% | {churn:>10.1f}%"
        )
    print("=" * 125 + "\n")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delta Options Microstructure Reporting Engine")
    parser.add_argument("--db", default=None, help=f"Path to SQLite database (default: {config.DB_PATH})")
    parser.add_argument("--underlying", default=None, help="Filter by underlying (BTC, ETH, XAUT)")
    args = parser.parse_args()
    generate_report(db_path=args.db, underlying=args.underlying)
