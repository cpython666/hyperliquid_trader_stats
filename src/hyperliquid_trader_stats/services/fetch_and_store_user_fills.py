import asyncio
import aiohttp
import logging
from hyperliquid_trader_stats.hyper_x_utils import fetch_user_fills, store_fills
from hyperliquid_trader_stats.db.collections import (web3_hyperliquid_hyper_x_addresses_collection,
                web3_hyperliquid_hyper_x_user_fills_summary_collection, web3_hyperliquid_vaults_collection)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")]
)
logger = logging.getLogger(__name__)

async def update_user_fills(addresses: list, batch_size=100):
    """
    批量获取并更新用户交易历史到 MongoDB，每次地址请求后立即存储。

    参数：
        addresses: list，包含地址和最后时间戳的列表
        batch_size: int，每批处理的地址数量
    """
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(addresses), batch_size):
            batch_addresses = addresses[i:i + batch_size]
            logger.info(f"📦 处理批次 {i // batch_size + 1}，包含 {len(batch_addresses)} 个地址")

            for addr_info in batch_addresses:
                address = addr_info["ethAddress"]
                last_time = addr_info.get("lastTime", 0)
                account_value = addr_info.get("accountValue", 0)
                effective_position_value = addr_info.get("effective_position_value", 0)
                fills = await fetch_user_fills(session, address, start_time=last_time)

                if fills is None:
                    logger.error(f"❌ 地址: {address} 余额 {account_value} 获取交易记录失败，跳过本次更新")
                    continue
                if len(fills) == 0:
                    logger.info(f"✅ 地址: {address} 余额 {account_value} 无新交易记录")
                    continue
                await store_fills(address, fills)

async def fetch_and_store_user_fills(limit: int = 100, incremental: bool = True):
    """
    获取并存储用户交易历史。
    去除金库数据

    参数：
        limit: int，限制处理的地址数量，默认为 100
        incremental: bool，是否增量更新，默认为 True
    """
    try:
        if incremental:
            # 增量模式：从冗余表获取已有地址
            cursor = web3_hyperliquid_hyper_x_user_fills_summary_collection.find({}, {"ethAddress": 1})
            existing_addresses = {doc["ethAddress"] async for doc in cursor}
            logger.info(f"📑 冗余表中已有 {len(existing_addresses)} 个地址")

            # 查询新地址
            cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
                {"marginSummary.accountValue": {"$exists": True},
                "effective_position_value": {"$exists": True},
                 "ethAddress": {"$nin": list(existing_addresses)}},
                {"ethAddress": 1, "marginSummary.accountValue": 1, "effective_position_value": 1}
            ).sort("marginSummary.accountValue", -1).limit(limit)

            addresses = [{"ethAddress": doc["ethAddress"], "lastTime": 0, "accountValue":doc.get("marginSummary", {}).get("accountValue", 0), "effective_position_value":doc.get("effective_position_value", 0)} async for doc in cursor]
            logger.info(f"🆕 增量模式：需要处理的地址数: {len(addresses)}")

        else:
            # 全量模式：从冗余表获取所有地址和最新时间
            cursor = web3_hyperliquid_hyper_x_user_fills_summary_collection.find({}, {"ethAddress": 1, "lastTime": 1})
            last_times = {doc["ethAddress"]: doc["lastTime"] async for doc in cursor}
            logger.info(f"📑 从冗余表获取 {len(last_times)} 个地址的最新时间")

            # 查询地址集合
            cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
                {"marginSummary.accountValue": {"$exists": True},
                "effective_position_value": {"$exists": True},
                 },
                {"ethAddress": 1, "marginSummary.accountValue": 1, "effective_position_value": 1}
            ).sort("effective_position_value", -1).limit(limit)

            addresses = [
                {"ethAddress": doc["ethAddress"], "lastTime": last_times.get(doc["ethAddress"], 0), "accountValue":doc.get("marginSummary", {}).get("accountValue", 0), "effective_position_value":doc.get("effective_position_value", 0)}
                async for doc in cursor
            ]
            logger.info(f"🔄 全量模式：需要处理的地址数: {len(addresses)}")
        print('去掉金库地址前地址数量：',len(addresses),addresses[:5])
        vaults_addresses={doc["vaultAddress"] async for doc in web3_hyperliquid_vaults_collection.find({}, {"vaultAddress": 1})}
        print('找到金库的地址数量：',len(vaults_addresses))
        addresses=[_ for _ in addresses if _["ethAddress"] not in vaults_addresses]
        print('去掉金库地址后地址数量：',len(addresses))
        if not addresses:
            logger.info("✅ 没有需要处理的新地址")
            return

        await update_user_fills(addresses)
        logger.info(f"🎉 完成 {len(addresses)} 个地址的交易记录更新")

    except Exception as e:
        logger.error(f"💥 主函数发生异常: {e}")
        raise

if __name__ == "__main__":
    try:
        # asyncio.run(fetch_and_store_user_fills(limit=30000, incremental=False))
        asyncio.run(fetch_and_store_user_fills(limit=30000, incremental=True))
    finally:
        logger.info("👋 关闭事件循环")
