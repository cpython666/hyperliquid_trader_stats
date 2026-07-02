import unittest
from datetime import datetime

from hyperliquid_trader_stats.analytics.compute_complete_trades import (
    calculate_trade_pnl_stats,
    _trade_documents,
    _datetime_to_milliseconds,
    _select_stale_addresses,
    _select_watermark_addresses,
)


class ComputeTradesSelectionTests(unittest.TestCase):
    def test_calculates_single_trade_net_pnl_stats(self):
        stats = calculate_trade_pnl_stats(
            [
                {"net_pnl": 10},
                {"net_pnl": "-4.5"},
                {"net_pnl": 20},
                {"net_pnl": -1},
            ]
        )

        self.assertEqual(
            stats,
            {
                "avg_trade_net": 6.13,
                "median_trade_net": 4.5,
                "max_profit_trade_net": 20.0,
                "max_loss_trade_net": -4.5,
            },
        )

    def test_trade_net_pnl_stats_default_to_zero_without_trades(self):
        self.assertEqual(
            calculate_trade_pnl_stats([]),
            {
                "avg_trade_net": 0.0,
                "median_trade_net": 0.0,
                "max_profit_trade_net": 0.0,
                "max_loss_trade_net": 0.0,
            },
        )

    def test_trade_documents_add_address_and_update_time(self):
        updated_at = datetime(2026, 7, 2)

        docs = _trade_documents(
            "0xabc",
            [{"coin": "BTC", "coin_index": 1, "net_pnl": 12.3}],
            updated_at,
        )

        self.assertEqual(
            docs,
            [
                {
                    "ethAddress": "0xabc",
                    "coin": "BTC",
                    "coin_index": 1,
                    "net_pnl": 12.3,
                    "updated_at": updated_at,
                }
            ],
        )

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
