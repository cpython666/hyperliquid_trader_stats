import asyncio
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from hyperliquid_trader_stats.cli import build_parser
from hyperliquid_trader_stats.cli import fetch_block_addresses_command


def test_cli_parses_fetch_user_fills_options():
    parser = build_parser()

    args = parser.parse_args(
        ["fetch-user-fills", "--limit", "10", "--no-incremental"]
    )

    assert args.command == "fetch-user-fills"
    assert args.limit == 10
    assert args.incremental is False


def test_cli_defaults_fetch_user_states_to_incremental():
    parser = build_parser()

    args = parser.parse_args(["fetch-user-states"])

    assert args.incremental is True
    assert args.updated_before is None


def test_cli_parses_fetch_user_states_full_refresh():
    parser = build_parser()

    args = parser.parse_args(["fetch-user-states", "--no-incremental"])

    assert args.incremental is False
    assert args.updated_before is None


def test_cli_parses_fetch_user_states_updated_before():
    parser = build_parser()

    args = parser.parse_args(
        ["fetch-user-states", "--updated-before", "2026-06-01"]
    )

    assert args.incremental is True
    assert args.updated_before == datetime(2026, 6, 1)


def test_cli_rejects_multiple_fetch_user_states_modes():
    parser = build_parser()

    try:
        parser.parse_args(
            [
                "fetch-user-states",
                "--no-incremental",
                "--updated-before",
                "2026-06-01",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("互斥的状态采集模式参数应解析失败")


def test_cli_parses_large_index_initialization_option():
    parser = build_parser()

    args = parser.parse_args(["init-db", "--include-large-indexes"])

    assert args.include_large_indexes is True


def test_cli_parses_compute_trades_stale_days():
    parser = build_parser()

    args = parser.parse_args(["compute-trades", "--stale-days", "7"])

    assert args.stale_days == 7
    assert args.updated_before is None


def test_cli_parses_compute_trades_updated_before():
    parser = build_parser()

    args = parser.parse_args(
        ["compute-trades", "--updated-before", "2026-06-01"]
    )

    assert args.updated_before == datetime(2026, 6, 1)
    assert args.stale_days is None


def test_cli_rejects_multiple_compute_trades_modes():
    parser = build_parser()

    try:
        parser.parse_args(
            [
                "compute-trades",
                "--stale-days",
                "7",
                "--updated-before",
                "2026-06-01",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("互斥的计算模式参数应解析失败")


def test_cli_exposes_expected_commands():
    parser = build_parser()
    subparser_action = next(
        action for action in parser._actions if action.dest == "command"
    )

    assert {
        "init-db",
        "fetch-leaderboard",
        "fetch-user-states",
        "fetch-user-fills",
        "compute-trades",
        "analyze-ls-rate",
        "analyze-history",
        "visualize-coin-value-ratio",
    }.issubset(subparser_action.choices)


def test_cli_allows_fetch_block_addresses_without_start_height():
    parser = build_parser()

    args = parser.parse_args(["fetch-block-addresses"])

    assert args.start_height is None
    assert args.block_count == 1000


def test_cli_accepts_fetch_block_addresses_start_height():
    parser = build_parser()

    args = parser.parse_args(["fetch-block-addresses", "651879309"])

    assert args.start_height == 651879309


def test_cli_parses_fetch_block_addresses_requests_backend():
    parser = build_parser()

    args = parser.parse_args(
        ["fetch-block-addresses", "651879309", "--requests", "--concurrency", "3"]
    )

    assert args.requests is True
    assert args.concurrency == 3


def test_cli_parses_analyze_history_defaults():
    parser = build_parser()

    args = parser.parse_args(["analyze-history"])

    assert args.basic is False
    assert args.mode == "group"
    assert args.export_excel == "analyze_result.xlsx"
    assert args.output_dir is None
    assert args.show is True


def test_cli_parses_analyze_history_big_no_show():
    parser = build_parser()

    args = parser.parse_args(
        ["analyze-history", "--mode", "big", "--output-dir", "plots_tmp", "--no-show"]
    )

    assert args.mode == "big"
    assert args.output_dir == "plots_tmp"
    assert args.show is False


def test_cli_parses_visualize_coin_value_ratio_defaults():
    parser = build_parser()

    args = parser.parse_args(["visualize-coin-value-ratio"])

    assert args.analysis_id is None
    assert args.winrate_key is None
    assert args.top == 30
    assert args.output_dir == "plots_tmp"
    assert args.show is True


def test_cli_parses_visualize_coin_value_ratio_options():
    parser = build_parser()

    args = parser.parse_args(
        [
            "visualize-coin-value-ratio",
            "--analysis-id",
            "686694116fc51490b88ff79f",
            "--winrate-key",
            "ge_80",
            "--top",
            "15",
            "--output-dir",
            "coin_plots",
            "--no-show",
        ]
    )

    assert args.analysis_id == "686694116fc51490b88ff79f"
    assert args.winrate_key == "ge_80"
    assert args.top == 15
    assert args.output_dir == "coin_plots"
    assert args.show is False


def test_fetch_block_addresses_uses_latest_height_when_omitted(monkeypatch):
    fetch = AsyncMock()
    get_height = Mock(return_value=651879309)
    module = SimpleNamespace(
        fetch_and_store_addresses_from_block=fetch,
        get_block_height=get_height,
    )
    monkeypatch.setitem(
        sys.modules,
        "hyperliquid_trader_stats.services.fetch_block_addresses",
        module,
    )
    args = SimpleNamespace(
        requests=False, start_height=None, block_count=1000, concurrency=None
    )

    asyncio.run(fetch_block_addresses_command(args))

    get_height.assert_called_once_with()
    fetch.assert_awaited_once_with(
        651879309,
        1000,
        backend="aiohttp",
        concurrency=None,
    )


def test_fetch_block_addresses_passes_requests_backend(monkeypatch):
    fetch = AsyncMock()
    module = SimpleNamespace(
        fetch_and_store_addresses_from_block=fetch,
        get_block_height=Mock(),
    )
    monkeypatch.setitem(
        sys.modules,
        "hyperliquid_trader_stats.services.fetch_block_addresses",
        module,
    )
    args = SimpleNamespace(
        requests=True, start_height=651879309, block_count=500, concurrency=7
    )

    asyncio.run(fetch_block_addresses_command(args))

    fetch.assert_awaited_once_with(
        651879309,
        500,
        backend="requests",
        concurrency=7,
    )
