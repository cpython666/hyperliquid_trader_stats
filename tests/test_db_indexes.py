import asyncio
from unittest.mock import AsyncMock, call

from pymongo import ASCENDING, DESCENDING

from hyperliquid_trader_stats.db import collections


def test_init_hyper_x_collections_creates_query_indexes(monkeypatch):
    collection_names = [
        "web3_hyperliquid_hyper_x_addresses_collection",
        "web3_hyperliquid_hyper_x_user_fills_collection",
        "web3_hyperliquid_hyper_x_user_fills_summary_collection",
        "web3_hyperliquid_hyper_x_completed_trades_collection",
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        "web3_hyperliquid_hyper_x_analyze_result_collection",
        "web3_hyperliquid_vaults_collection",
    ]
    mocked_collections = {}
    for name in collection_names:
        mocked_collection = AsyncMock()
        mocked_collection.name = name
        mocked_collection.index_information.return_value = {}
        mocked_collections[name] = mocked_collection
        monkeypatch.setattr(collections, name, mocked_collection)

    asyncio.run(collections.init_hyper_x_collections(include_large_indexes=True))

    addresses_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_addresses_collection"
    ].create_index.await_args_list
    assert call(
        [("marginSummary.accountValue", DESCENDING), ("ethAddress", ASCENDING)],
        name="account_value_desc_eth_address",
    ) in addresses_calls
    assert call(
        [("effective_position_value", DESCENDING), ("ethAddress", ASCENDING)],
        name="effective_position_value_desc_eth_address",
    ) in addresses_calls

    fills_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_user_fills_collection"
    ].create_index.await_args_list
    assert call(
        [("ethAddress", ASCENDING), ("time", ASCENDING)],
        name="eth_address_time",
    ) in fills_calls

    summary_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_user_fills_summary_collection"
    ].create_index.await_args_list
    assert call(
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    ) in summary_calls

    completed_trades_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_completed_trades_collection"
    ].create_index.await_args_list
    assert call(
        [("ethAddress", ASCENDING), ("coin", ASCENDING), ("coin_index", ASCENDING)],
        unique=True,
        name="unique_eth_address_coin_index",
    ) in completed_trades_calls
    assert call(
        [("ethAddress", ASCENDING), ("end_time_ms", DESCENDING)],
        name="eth_address_end_time_desc",
    ) in completed_trades_calls

    trade_summary_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_trade_summary_collection"
    ].create_index.await_args_list
    assert call(
        [("updated_at", ASCENDING), ("ethAddress", ASCENDING)],
        name="updated_at_eth_address",
    ) in trade_summary_calls
    assert call(
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    ) in trade_summary_calls
    assert call(
        [
            ("total_trades", ASCENDING),
            ("win_rate_score", DESCENDING),
            ("win_rate", DESCENDING),
            ("ethAddress", ASCENDING),
        ],
        name="total_trades_rank_fields",
    ) in trade_summary_calls
    assert call(
        [("completed_trade_pnl.net", DESCENDING), ("ethAddress", ASCENDING)],
        name="net_pnl_desc_eth_address",
    ) in trade_summary_calls
    expected_pnl_stat_indexes = {
        "avg_trade_net_desc_eth_address": "completed_trade_pnl.avg_trade_net",
        "median_trade_net_desc_eth_address": "completed_trade_pnl.median_trade_net",
        "max_profit_trade_net_desc_eth_address": (
            "completed_trade_pnl.max_profit_trade_net"
        ),
        "max_loss_trade_net_desc_eth_address": (
            "completed_trade_pnl.max_loss_trade_net"
        ),
    }
    for index_name, field_name in expected_pnl_stat_indexes.items():
        assert call(
            [(field_name, DESCENDING), ("ethAddress", ASCENDING)],
            name=index_name,
        ) in trade_summary_calls

    expected_win_rate_indexes = {
        "win_rate_desc_eth_address": "win_rate",
        "win_rate_score_desc_eth_address": "win_rate_score",
        "win_rate_over_1w_desc_eth_address": (
            "entry_value_summary.win_rate_over_1w.win_rate"
        ),
        "win_rate_over_10w_desc_eth_address": (
            "entry_value_summary.win_rate_over_10w.win_rate"
        ),
        "win_rate_over_100w_desc_eth_address": (
            "entry_value_summary.win_rate_over_100w.win_rate"
        ),
        "win_rate_over_1000w_desc_eth_address": (
            "entry_value_summary.win_rate_over_1000w.win_rate"
        ),
    }
    for index_name, field_name in expected_win_rate_indexes.items():
        assert call(
            [(field_name, DESCENDING), ("ethAddress", ASCENDING)],
            name=index_name,
        ) in trade_summary_calls

    analyze_result_calls = mocked_collections[
        "web3_hyperliquid_hyper_x_analyze_result_collection"
    ].create_index.await_args_list
    assert call(
        [("timestamp", ASCENDING)],
        name="timestamp_asc",
    ) in analyze_result_calls


def test_ensure_index_reuses_equivalent_index_with_different_name():
    collection = AsyncMock()
    collection.name = "vaults"
    collection.index_information.return_value = {
        "vaultAddress_1": {
            "key": [("vaultAddress", ASCENDING)],
            "unique": True,
        }
    }

    result = asyncio.run(
        collections._ensure_index(
            collection,
            [("vaultAddress", ASCENDING)],
            unique=True,
            name="unique_vault_address",
        )
    )

    assert result == "vaultAddress_1"
    collection.create_index.assert_not_awaited()
