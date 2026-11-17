"""
src/config.py
Configuration constants and trading window schedules for Delta Options Microstructure engine.
Zero-dependency Python 3 standard library.
"""

import os
from datetime import time, timedelta, timezone
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "options_microstructure.db"

# API Endpoints & Headers
DELTA_BASE_URL = "https://api.india.delta.exchange"
DEFAULT_USER_AGENT = "Delta-Options-Microstructure/1.0"
API_TIMEOUT = 10  # seconds

# Target Underlyings
TARGET_UNDERLYINGS = ("BTC", "ETH", "PAXG", "XAUT")

# Polling Settings
DEFAULT_POLL_INTERVAL = 5.0  # seconds
BATCH_SIZE = 50  # buffer size before SQLite commit
SPOT_BUFFER_WINDOW_SEC = 60  # seconds for rolling 1-minute spot change calculation

# Timezone (IST: UTC + 5:30)
IST = timezone(timedelta(hours=5, minutes=30))
DELTA_SETTLEMENT_HOUR_UTC = 12  # Daily settlement at 12:00 UTC (17:30 IST)

# High-Frequency IST Trading Windows for Daemon
# Formats: (start_time, end_time, label)
DAEMON_IST_WINDOWS = [
    (time(9, 45), time(10, 30), "Morning Entry Window"),
    (time(13, 30), time(13, 45), "Mid-Day Window"),
    (time(16, 45), time(17, 25), "Evening Exit & Expiry Window"),
]

# Delta Bands
DELTA_BANDS = [
    ("FAR_OTM_<0.07", 0.0, 0.07),
    ("0.07-0.11", 0.07, 0.11),
    ("0.11-0.14", 0.11, 0.14),
    ("0.14-0.18", 0.14, 0.18),
    ("0.18-0.25", 0.18, 0.25),
    ("ATM_0.25-0.55", 0.25, 0.55),
    ("ITM_>0.55", 0.55, 999.0),
]
