import asyncio

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

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


async def init_hyper_x_collections():
    """创建 HyperX 相关集合索引。"""
    await web3_hyperliquid_hyper_x_addresses_collection.create_index(
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await web3_hyperliquid_hyper_x_user_fills_collection.create_index(
        [("ethAddress", ASCENDING), ("tid", ASCENDING)],
        unique=True,
        name="unique_eth_address_tid",
    )
    await web3_hyperliquid_hyper_x_completed_trades_collection.create_index(
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await web3_hyperliquid_hyper_x_trade_summary_collection.create_index(
        [("ethAddress", ASCENDING)],
        unique=True,
        name="unique_eth_address",
    )
    await web3_hyperliquid_vaults_collection.create_index(
        [("vaultAddress", ASCENDING)],
        unique=True,
        name="unique_vault_address",
    )
    print("已成功创建 HyperX 相关集合和索引。")


if __name__ == "__main__":
    asyncio.run(init_hyper_x_collections())
