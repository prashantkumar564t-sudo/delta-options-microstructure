"""
src/delta_api.py
Lightweight Delta Exchange REST API client with RTT latency profiling.
Built strictly using Python 3 Standard Library (urllib).
"""

import json
import time
import urllib.error
import urllib.request
from typing import List, Optional

from src import config


class DeltaAPI:
    """Lightweight HTTP REST client for Delta Exchange India."""

    def __init__(self, base_url: str = config.DELTA_BASE_URL, timeout: int = config.API_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.last_rtt_ns = 0

    def get(self, endpoint: str) -> Optional[dict]:
        """Send a public GET request, record round-trip latency, and return parsed JSON result."""
        url = f"{self.base_url}{endpoint}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": config.DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
            method="GET",
        )

        t_start = time.perf_counter_ns()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.last_rtt_ns = time.perf_counter_ns() - t_start
                if response.status != 200:
                    raise RuntimeError(f"Unexpected HTTP status: {response.status}")
                raw_data = response.read()
                data = json.loads(raw_data.decode("utf-8"))
                if not data.get("success", False):
                    raise RuntimeError(f"Delta API error: {data}")
                return data.get("result")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            self.last_rtt_ns = time.perf_counter_ns() - t_start
            raise RuntimeError(f"API request failed on {endpoint}: {e}") from e

    @property
    def last_rtt_ms(self) -> float:
        """Return the last measured RTT latency in milliseconds."""
        return self.last_rtt_ns / 1_000_000.0

    def fetch_tickers(self) -> List[dict]:
        """Fetch all market tickers from Delta bulk snapshot endpoint."""
        res = self.get("/v2/tickers")
        return res if isinstance(res, list) else []
