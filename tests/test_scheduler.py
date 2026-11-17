"""
tests/test_scheduler.py
Unit tests for IST window scheduler logic and state transitions.
"""

import unittest
from datetime import datetime, timezone, timedelta
from scheduler import get_current_window_state
from src import config


class TestScheduler(unittest.TestCase):
    """Test suite for IST trading window scheduling logic."""

    def test_inside_morning_window(self):
        # 10:00 AM IST
        test_dt = datetime(2026, 11, 14, 10, 0, 0, tzinfo=config.IST)
        is_active, label, sec = get_current_window_state(current_time=test_dt)
        self.assertTrue(is_active)
        self.assertEqual(label, "Morning Entry Window")
        # 10:00 to 10:30 is 30 minutes = 1800 seconds
        self.assertEqual(sec, 1800)

    def test_inside_midday_window(self):
        # 13:35 IST
        test_dt = datetime(2026, 11, 14, 13, 35, 0, tzinfo=config.IST)
        is_active, label, sec = get_current_window_state(current_time=test_dt)
        self.assertTrue(is_active)
        self.assertEqual(label, "Mid-Day Window")
        # 13:35 to 13:45 is 10 minutes = 600 seconds
        self.assertEqual(sec, 600)

    def test_inside_evening_window(self):
        # 17:00 IST
        test_dt = datetime(2026, 11, 14, 17, 0, 0, tzinfo=config.IST)
        is_active, label, sec = get_current_window_state(current_time=test_dt)
        self.assertTrue(is_active)
        self.assertEqual(label, "Evening Exit & Expiry Window")
        # 17:00 to 17:25 is 25 minutes = 1500 seconds
        self.assertEqual(sec, 1500)

    def test_outside_window_morning_idle(self):
        # 08:00 AM IST -> should target Morning Entry Window at 09:45 (1h 45m = 6300 seconds)
        test_dt = datetime(2026, 11, 14, 8, 0, 0, tzinfo=config.IST)
        is_active, label, sec = get_current_window_state(current_time=test_dt)
        self.assertFalse(is_active)
        self.assertEqual(label, "Morning Entry Window")
        self.assertEqual(sec, 6300)

    def test_outside_window_night_idle(self):
        # 22:00 IST -> should target tomorrow's Morning Entry Window at 09:45 (11h 45m = 42300 seconds)
        test_dt = datetime(2026, 11, 14, 22, 0, 0, tzinfo=config.IST)
        is_active, label, sec = get_current_window_state(current_time=test_dt)
        self.assertFalse(is_active)
        self.assertEqual(label, "Morning Entry Window")
        self.assertEqual(sec, 42300)


if __name__ == "__main__":
    unittest.main()
