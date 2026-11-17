"""
launcher.py
Unified CLI entry point for Delta Options Microstructure engine.
Supports manual sampling runs and continuous scheduled IST window daemon mode.
Zero-dependency Python 3 standard library.
"""

import argparse
import sys
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from report import generate_report
from scheduler import run_daemon
from src import config
from src.collector import run_microstructure_collector


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delta Options Microstructure Telemetry & IST Window Daemon"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as persistent daemon locked to IST quant windows (09:45-10:30, 13:30-13:45, 16:45-17:25 IST)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Manual collection run duration in seconds (default: 300; 0 for infinite)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=config.DEFAULT_POLL_INTERVAL,
        help=f"Polling interval in seconds (default: {config.DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--underlyings",
        default="BTC,ETH,PAXG,XAUT",
        help="Comma-separated underlying assets (default: BTC,ETH,PAXG,XAUT)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help=f"Custom SQLite database path (default: {config.DB_PATH})",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate and print analytical report after manual run",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    underlyings = tuple(u.strip().upper() for u in args.underlyings.split(",") if u.strip())
    db_path = Path(args.db) if args.db else None

    if args.daemon:
        run_daemon(interval=args.interval, underlyings=underlyings, db_path=db_path)
    else:
        metrics = run_microstructure_collector(
            duration=args.duration,
            interval=args.interval,
            underlyings=underlyings,
            db_path=db_path,
            verbose=True,
        )
        if args.report:
            generate_report(db_path=db_path, since_timestamp_us=metrics["start_us"])


if __name__ == "__main__":
    main()
