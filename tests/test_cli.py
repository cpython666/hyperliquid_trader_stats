import asyncio
import sys
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


def test_cli_parses_large_index_initialization_option():
    parser = build_parser()

    args = parser.parse_args(["init-db", "--include-large-indexes"])

    assert args.include_large_indexes is True


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


def test_fetch_block_addresses_uses_latest_height_when_omitted(monkeypatch):
    fetch = AsyncMock()
    get_height = Mock(return_value=651879309)
    module = SimpleNamespace(
        fetch_and_store_addresses_from_block=fetch,
        get_block_height=get_height,
    )
    monkeypatch.setitem(
        sys.modules,
        "hyperliquid_trader_stats.services.fetch_and_store_addresses_from_block",
        module,
    )
    args = SimpleNamespace(requests=False, start_height=None, block_count=1000)

    asyncio.run(fetch_block_addresses_command(args))

    get_height.assert_called_once_with()
    fetch.assert_awaited_once_with(651879309, 1000)
