"""
scheduler.py
Automated IST trading window scheduler & daemon for Delta Options Microstructure.
Monitors the 3 key daily quant windows with high-frequency 5s sampling,
and maintains a low-power smart heartbeat outside active windows.
Zero-dependency Python 3 standard library.
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from src import config
from src.collector import run_microstructure_collector, trim_process_memory


def get_current_window_state(current_time: Optional[datetime] = None) -> Tuple[bool, str, int]:
    """
    Evaluates current IST time against the 3 target trading windows:
    - Morning: 09:45 - 10:30 IST
    - Mid-Day: 13:30 - 13:45 IST
    - Evening: 16:45 - 17:25 IST

    Returns:
        (is_active, window_label, duration_or_wait_seconds)
    """
    now_ist = current_time.astimezone(config.IST) if current_time else datetime.now(config.IST)
    current_t = now_ist.time()
    today_date = now_ist.date()

    # 1. Check if inside any active window
    for start_t, end_t, label in config.DAEMON_IST_WINDOWS:
        if start_t <= current_t < end_t:
            end_dt = datetime.combine(today_date, end_t, tzinfo=config.IST)
            remaining_sec = max(1, int((end_dt - now_ist).total_seconds()))
            return True, label, remaining_sec

    # 2. Outside active windows: compute next upcoming window
    upcoming = []
    for start_t, end_t, label in config.DAEMON_IST_WINDOWS:
        start_dt = datetime.combine(today_date, start_t, tzinfo=config.IST)
        if start_dt > now_ist:
            upcoming.append((start_dt, label))

    # If all windows for today have passed, target tomorrow's first window
    if not upcoming:
        tomorrow = today_date + timedelta(days=1)
        first_start_t, _, first_label = config.DAEMON_IST_WINDOWS[0]
        start_dt = datetime.combine(tomorrow, first_start_t, tzinfo=config.IST)
        upcoming.append((start_dt, first_label))

    next_start_dt, next_label = sorted(upcoming, key=lambda x: x[0])[0]
    seconds_to_wait = max(1, int((next_start_dt - now_ist).total_seconds()))
    return False, next_label, seconds_to_wait


def run_daemon(
    interval: float = config.DEFAULT_POLL_INTERVAL,
    underlyings: Tuple[str, ...] = config.TARGET_UNDERLYINGS,
    db_path: Optional[Path] = None,
):
    """
    Continuous daemon running in persistent tmux or service:
    - High-frequency 5s sampling inside designated IST windows
    - Smart idle sleep with 5-minute heartbeat outside windows
    """
    print("=" * 80)
    print("Starting Delta Options Microstructure Automated IST Window Daemon")
    print("High-Frequency Sampling Windows (IST):")
    for start_t, end_t, label in config.DAEMON_IST_WINDOWS:
        print(f"  - {label:<32}: {start_t.strftime('%H:%M')} -> {end_t.strftime('%H:%M')} IST")
    print("=" * 80)

    try:
        while True:
            is_active, label, sec = get_current_window_state()

            if is_active:
                now_str = datetime.now(config.IST).strftime("%H:%M:%S")
                print(f"\n[ACTIVE WINDOW] Entering '{label}' at {now_str} IST. Duration: {sec}s ({sec/60:.1f}m)...")
                run_microstructure_collector(
                    duration=sec,
                    interval=interval,
                    underlyings=underlyings,
                    db_path=db_path,
                    verbose=True,
                )
                print(f"[WINDOW COMPLETE] '{label}' session finished successfully.")
                trim_process_memory()
            else:
                # Outside window: Smart idle sleep with periodic heartbeats (every 300s / 5m)
                sleep_chunk = min(sec, 300)
                hours, rem = divmod(sec, 3600)
                minutes, _ = divmod(rem, 60)
                now_str = datetime.now(config.IST).strftime("%H:%M:%S")
                sys.stdout.write(
                    f"\r[HEARTBEAT {now_str} IST] Idle. Next window: '{label}' in {hours:02d}h {minutes:02d}m ({sec}s). Sleeping {sleep_chunk}s... "
                )
                sys.stdout.flush()
                trim_process_memory()
                time.sleep(sleep_chunk)

    except KeyboardInterrupt:
        print("\n[!] Daemon terminated by user.")


if __name__ == "__main__":
    run_daemon()
