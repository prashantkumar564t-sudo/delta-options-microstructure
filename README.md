# Delta Options Microstructure Telemetry Engine (`delta-options-microstructure`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Standard%20Library%20Only-brightgreen.svg)]()
[![Database](https://img.shields.io/badge/Database-SQLite%20WAL-orange.svg)]()

Institutional-grade, zero-dependency options microstructure telemetry collector, quantitative liquidity auditor, and automated IST trading window daemon for **Delta Exchange India** derivatives.

Monitors live order book divergence, mark price haircuts, and liquidity depth across **all active expiries** (`0-DTE`, `1-DTE`, `2-DTE`, `WEEKLY`, `MONTHLY`) for **Bitcoin (BTC)**, **Ethereum (ETH)**, and **Gold (XAUT / PAXG)** options.

---

## 🌟 Key Features

- **Pure Python 3 Standard Library:** Zero `pip install` requirements. Uses only built-in `urllib.request`, `sqlite3`, `time`, `json`, `datetime`, and `collections.deque`.
- **Lossless SQLite WAL Persistence:** High-throughput write-ahead logging (`PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`) with memory temp store and batch buffer commits into `data/options_microstructure.db`.
- **Strict Memory Discipline:** Memory-trimmed working set (<30 MB RAM) engineered for reliable 24/7 background execution on mobile Linux servers (Android Termux) and cloud micro-instances.
- **Microstructure & Friction Metrics:**
  - `spread_vs_mark_pct`: `(best_ask - best_bid) / mark_price * 100`
  - `bid_slippage_pct`: `(mark_price - best_bid) / mark_price * 100` (haircut on immediate limit/market sell)
  - `ltp_mark_spike_pct`: `(ltp - mark_price) / mark_price * 100`
  - `quote_changed`: Boolean flag detecting real-time quote updates vs static orderbooks
  - `spot_1m_change_pct`: In-memory sliding buffer measuring instantaneous 1-minute underlying velocity.
- **Automated IST Window Daemon:** High-frequency (5s) bursts locked to Delta Exchange quantitative execution cycles:
  - **Morning Entry Window:** `09:45 AM – 10:30 AM IST`
  - **Mid-Day Window:** `01:30 PM – 01:45 PM IST`
  - **Evening Exit & Expiry Window:** `04:45 PM – 05:25 PM IST`
  - Outside windows: Deep sleep with a 5-minute low-power heartbeat log.

---

## 📂 Project Architecture

```
delta-options-microstructure/
├── .gitignore
├── LICENSE                          # MIT License
├── README.md
├── launcher.py                      # Unified CLI entry point
├── scheduler.py                     # Automated IST window daemon
├── report.py                        # Expiry & delta-band analytics reporter
├── src/
│   ├── __init__.py
│   ├── config.py                    # Window schedules & delta band constants
│   ├── delta_api.py                 # Lightweight REST API client with RTT profiling
│   ├── instruments.py               # Expiry/delta classifier & microstructure formulas
│   ├── storage.py                   # SQLite WAL engine with buffering
│   └── collector.py                 # Core telemetry scanning loop
├── tests/
│   ├── __init__.py
│   ├── test_instruments.py          # 100% coverage on parsing & formulas
│   ├── test_storage.py              # Schema, pragmas & persistence tests
│   └── test_scheduler.py            # IST window transitions & idle state tests
└── data/
    └── options_microstructure.db    # SQLite WAL database
```

---

## 🚀 Quickstart & Usage

### 1. Manual Collection Run
Collect options microstructure for 60 seconds (or custom duration) and print summary:
```bash
python launcher.py --duration 60 --interval 5 --report
```

### 2. Continuous Automated Daemon Mode
Run continuously inside `tmux` or as a background service. It will wake up for the 3 target IST windows and maintain a low-power heartbeat outside them:
```bash
python launcher.py --daemon
```

### 3. Generate Analytical Report
Inspect database contents with aggregated statistics grouped by underlying, expiry, and delta band:
```bash
python report.py
```

### 4. Run Test Suite
```bash
python -m unittest discover tests
```

---

## 📊 Database Schema (`options_microstructure`)

| Column | Type | Description |
| :--- | :--- | :--- |
| `timestamp_us` | `INTEGER` | Epoch timestamp in microseconds |
| `datetime_ist` | `TEXT` | Human-readable IST datetime (`YYYY-MM-DD HH:MM:SS`) |
| `underlying` | `TEXT` | `BTC`, `ETH`, `XAUT` / `PAXG` |
| `symbol` | `TEXT` | Option symbol (e.g., `C-BTC-95000-141126`) |
| `expiry_date` | `TEXT` | Expiry date (`YYYY-MM-DD`) |
| `expiry_bucket` | `TEXT` | `0-DTE`, `1-DTE`, `2-DTE`, `WEEKLY`, `MONTHLY` |
| `option_type` | `TEXT` | `CE` (Call) or `PE` (Put) |
| `strike` | `REAL` | Strike price |
| `delta` | `REAL` | Option Delta from exchange Black-76 Greeks |
| `delta_band` | `TEXT` | `FAR_OTM_<0.07`, `0.07-0.11`, `0.11-0.14`, `0.14-0.18`, `0.18-0.25`, `ATM_0.25-0.55`, `ITM_>0.55` |
| `iv` | `REAL` | Implied Volatility |
| `spot_price` | `REAL` | Live perpetual index/spot price |
| `spot_1m_change_pct` | `REAL` | 60-second rolling spot return (%) |
| `mark_price` | `REAL` | Delta Exchange mark price |
| `ltp` | `REAL` | Last traded price |
| `best_bid` | `REAL` | Top-of-book bid price |
| `best_ask` | `REAL` | Top-of-book ask price |
| `bid_size` | `REAL` | Contracts available at top bid |
| `ask_size` | `REAL` | Contracts available at top ask |
| `volume_24h` | `REAL` | 24-hour trading volume |
| `oi` | `REAL` | Open interest |
| `spread_vs_mark_pct` | `REAL` | `(best_ask - best_bid) / mark_price * 100` |
| `bid_slippage_pct` | `REAL` | `(mark_price - best_bid) / mark_price * 100` |
| `ltp_mark_spike_pct` | `REAL` | `(ltp - mark_price) / mark_price * 100` |
| `quote_changed` | `INTEGER` | `1` if bid/ask changed since previous scan; `0` if static |

**Primary Key:** `(symbol, timestamp_us)`

---

## 🛡️ Security & Zero Dependencies

- No external packages required.
- No hardcoded API keys or secrets.
- Read-only queries to public endpoints for safe quantitative research.

---

## 📜 License

[MIT License](LICENSE) © 2026 Prashant Kumar
