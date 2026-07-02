import asyncio

import pytest
from bson import ObjectId

from hyperliquid_trader_stats.plotting import visualize_coin_value_ratio as viz


class _FakeAnalyzeResultCollection:
    def __init__(self, result):
        self.result = result
        self.last_query = None
        self.last_sort = None

    async def find_one(self, query, *args, **kwargs):
        self.last_query = query
        self.last_sort = kwargs.get("sort")
        return self.result


def test_prepare_single_winrate_rows_sorts_infinite_ratios_first():
    snapshot = {
        "coin_position_distribution": {
            "BTC": {
                "ge_50": {
                    "long": 2,
                    "short": 1,
                    "long_value_sum": 100,
                    "short_value_sum": -25,
                }
            },
            "ETH": {
                "ge_50": {
                    "long": 1,
                    "short": 0,
                    "long_value_sum": 50,
                    "short_value_sum": 0,
                }
            },
            "SOL": {
                "ge_50": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 20,
                    "short_value_sum": -10,
                }
            },
        }
    }

    rows = viz.prepare_single_winrate_rows(snapshot, winrate_key="ge_50")

    assert [row["coin"] for row in rows] == ["ETH", "BTC", "SOL"]
    assert rows[0]["display_ratio"] == "∞"
    assert rows[1]["value_ratio"] == 4
    assert rows[2]["value_ratio"] == 2


def test_prepare_single_winrate_rows_sorts_by_selected_winrate_ratio():
    snapshot = {
        "coin_position_distribution": {
            "BTC": {
                "ge_90": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 50,
                    "short_value_sum": -10,
                }
            },
            "ETH": {
                "ge_90": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 20,
                    "short_value_sum": -10,
                }
            },
            "SOL": {
                "ge_50": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 1000,
                    "short_value_sum": -10,
                }
            },
        }
    }

    rows = viz.prepare_single_winrate_rows(snapshot, winrate_key="ge_90")

    assert [row["coin"] for row in rows] == ["BTC", "ETH"]
    assert [row["value_ratio"] for row in rows] == [5, 2]


def test_prepare_grouped_coin_rows_sorts_by_ge50_position_value_sum():
    snapshot = {
        "coin_position_distribution": {
            "BTC": {
                "eq_100": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 1000,
                    "short_value_sum": -10,
                },
                "ge_50": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 30,
                    "short_value_sum": -10,
                },
            },
            "ETH": {
                "ge_50": {
                    "long": 1,
                    "short": 1,
                    "long_value_sum": 80,
                    "short_value_sum": -10,
                }
            },
        }
    }

    rows = viz.prepare_grouped_coin_rows(snapshot)

    assert [row["coin"] for row in rows] == ["ETH", "BTC"]
    assert rows[0]["ge50_position_value_sum"] == 90
    assert rows[1]["ge50_position_value_sum"] == 40


def test_ratio_label_uses_raw_ratio_not_plot_substitute():
    assert viz._format_ratio_label("∞") == "∞"
    assert viz._format_ratio_label(float("inf")) == "∞"
    assert viz._format_ratio_label(204904.18) == "204904.18"
    assert viz._format_ratio_label(1.23456) == "1.235"


def test_plot_ratios_do_not_expand_axis_for_infinity_or_extreme_values():
    rows = [
        {"value_ratio": float("inf"), "display_ratio": "∞"},
        {"value_ratio": 1.0, "display_ratio": 1.0},
        {"value_ratio": 2.0, "display_ratio": 2.0},
        {"value_ratio": 10_000.0, "display_ratio": 10_000.0},
    ]

    cap = viz._plot_axis_cap(rows)
    plot_values = viz._safe_ratio_for_plot(rows)

    assert plot_values[0] == cap * 0.012
    assert plot_values[-1] == cap
    assert cap < 10_000
    assert viz._format_plot_label(rows[0], cap) == "∞"
    assert viz._format_plot_label(rows[-1], cap) == "// 10000.00"


def test_load_analysis_snapshot_uses_latest_when_id_omitted(monkeypatch):
    collection = _FakeAnalyzeResultCollection({"timestamp": "latest"})
    monkeypatch.setattr(
        viz,
        "web3_hyperliquid_hyper_x_analyze_result_collection",
        collection,
    )

    result = asyncio.run(viz.load_analysis_snapshot())

    assert result == {"timestamp": "latest"}
    assert collection.last_query == {}
    assert collection.last_sort == [("timestamp", -1)]


def test_load_analysis_snapshot_uses_object_id(monkeypatch):
    object_id = ObjectId()
    collection = _FakeAnalyzeResultCollection({"_id": object_id})
    monkeypatch.setattr(
        viz,
        "web3_hyperliquid_hyper_x_analyze_result_collection",
        collection,
    )

    result = asyncio.run(viz.load_analysis_snapshot(str(object_id)))

    assert result == {"_id": object_id}
    assert collection.last_query == {"_id": object_id}


def test_load_analysis_snapshot_rejects_invalid_object_id():
    with pytest.raises(ValueError, match="无效的 MongoDB ObjectId"):
        asyncio.run(viz.load_analysis_snapshot("not-an-object-id"))
