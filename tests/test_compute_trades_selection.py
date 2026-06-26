import unittest
from datetime import datetime

from hyperliquid_trader_stats.analytics.compute_complete_trades import (
    _datetime_to_milliseconds,
    _select_stale_addresses,
    _select_watermark_addresses,
)


class ComputeTradesSelectionTests(unittest.TestCase):
    def test_selects_new_and_changed_fill_watermarks(self):
        addresses = [
            "new",
            "unscored",
            "changed",
            "unchanged",
            "legacy_changed",
            "legacy_unchanged",
        ]
        completed_by_address = {
            "unscored": {"ethAddress": "unscored"},
            "changed": {
                "win_rate_score": 80,
                "processedThroughTime": 100,
            },
            "unchanged": {
                "win_rate_score": 80,
                "processedThroughTime": 200,
            },
            "legacy_changed": {
                "win_rate_score": 80,
                "updated_at": datetime(2026, 6, 1),
            },
            "legacy_unchanged": {
                "win_rate_score": 80,
                "updated_at": datetime(2026, 6, 2),
            },
        }
        last_fill_times = {
            "changed": 101,
            "unchanged": 200,
            "legacy_changed": _datetime_to_milliseconds(datetime(2026, 6, 2)),
            "legacy_unchanged": _datetime_to_milliseconds(datetime(2026, 6, 1)),
        }

        selected = _select_watermark_addresses(
            addresses,
            completed_by_address,
            last_fill_times,
        )

        self.assertEqual(selected, ["new", "unscored", "changed", "legacy_changed"])

    def test_selects_new_and_stale_addresses(self):
        selected = _select_stale_addresses(
            ["new", "stale", "recent"],
            {"stale", "recent"},
            {"stale"},
        )

        self.assertEqual(selected, ["new", "stale"])


if __name__ == "__main__":
    unittest.main()
