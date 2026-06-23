import asyncio

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from hyperliquid_trader_stats.config import MONGODB_DB_NAME, MONGODB_URL


mongo_client = AsyncIOMotorClient(MONGODB_URL)
mongo_db = mongo_client[MONGODB_DB_NAME]

web3_hyperliquid_vaults_collection = mongo_db["web3_hyperliquid_vaults"]

web3_hyperliquid_hyper_x_addresses_collection = mongo_db[
    "web3_hyperliquid_hyper_x_addresses"
]
web3_hyperliquid_hyper_x_user_fills_collection = mongo_db[
    "web3_hyperliquid_hyper_x_user_fills"
]
web3_hyperliquid_hyper_x_user_fills_summary_collection = mongo_db[
    "web3_hyperliquid_hyper_x_user_fills_summary"
]
web3_hyperliquid_hyper_x_completed_trades_collection = mongo_db[
    "web3_hyperliquid_hyper_x_completed_trades"
]
web3_hyperliquid_hyper_x_trade_summary_collection = mongo_db[
    "web3_hyperliquid_hyper_x_trade_summary"
]
web3_hyperliquid_hyper_x_analyze_result_collection = mongo_db[
    "web3_hyperliquid_hyper_x_analyze_result"
]


async def _ensure_index(collection, keys, *, name, **options):
    """复用定义相同的已有索引，否则按指定名称创建索引。"""
    index_information = await collection.index_information()
    target_keys = list(keys)
    target_unique = bool(options.get("unique", False))
    target_sparse = bool(options.get("sparse", False))
    target_partial_filter = options.get("partialFilterExpression")

    for existing_name, definition in index_information.items():
        if (
            list(definition.get("key", [])) == target_keys
            and bool(definition.get("unique", False)) == target_unique
            and bool(definition.get("sparse", False)) == target_sparse
            and definition.get("partialFilterExpression") == target_partial_filter
        ):
            print(f"索引已存在，跳过：{collection.name}.{existing_name}")
            return existing_name

    if name in index_information:
        raise RuntimeError(
            f"索引名称冲突：{collection.name}.{name} 已存在，但字段或选项不同。"
        )

    index_name = await collection.create_index(keys, name=name, **options)
    print(f"索引创建成功：{collection.name}.{index_name}")
    return index_name


async def init_hyper_x_collections(include_large_indexes: bool = False):
    """创建 HyperX 相关集合索引。"""
    await _ensure_index(
        web3_hyperliquid_hyper_x_addresses_collection,
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_addresses_collection,
        [("marginSummary.accountValue", DESCENDING), ("ethAddress", ASCENDING)],
        name="account_value_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_addresses_collection,
        [("effective_position_value", DESCENDING), ("ethAddress", ASCENDING)],
        name="effective_position_value_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_user_fills_collection,
        [("ethAddress", ASCENDING), ("tid", ASCENDING)],
        unique=True,
        name="unique_eth_address_tid",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_user_fills_summary_collection,
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [("win_rate", DESCENDING), ("ethAddress", ASCENDING)],
        name="win_rate_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [
            ("entry_value_summary.win_rate_over_1w.win_rate", DESCENDING),
            ("ethAddress", ASCENDING),
        ],
        name="win_rate_over_1w_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [
            ("entry_value_summary.win_rate_over_10w.win_rate", DESCENDING),
            ("ethAddress", ASCENDING),
        ],
        name="win_rate_over_10w_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [
            ("entry_value_summary.win_rate_over_100w.win_rate", DESCENDING),
            ("ethAddress", ASCENDING),
        ],
        name="win_rate_over_100w_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_completed_trades_collection,
        [
            ("entry_value_summary.win_rate_over_1000w.win_rate", DESCENDING),
            ("ethAddress", ASCENDING),
        ],
        name="win_rate_over_1000w_desc_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_trade_summary_collection,
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await _ensure_index(
        web3_hyperliquid_hyper_x_analyze_result_collection,
        [("timestamp", ASCENDING)],
        name="timestamp_asc",
    )
    await _ensure_index(
        web3_hyperliquid_vaults_collection,
        [("vaultAddress", ASCENDING)],
        unique=True,
        name="unique_vault_address",
    )

    if include_large_indexes:
        await _ensure_index(
            web3_hyperliquid_hyper_x_user_fills_collection,
            [("ethAddress", ASCENDING), ("time", ASCENDING)],
            name="eth_address_time",
        )
    else:
        print("已跳过大表索引：web3_hyperliquid_hyper_x_user_fills.eth_address_time")

    print("已成功创建 HyperX 相关集合和索引。")


if __name__ == "__main__":
    asyncio.run(init_hyper_x_collections())
