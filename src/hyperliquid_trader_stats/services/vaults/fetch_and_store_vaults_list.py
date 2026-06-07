import asyncio
import aiohttp
import logging
import time
from pymongo.operations import UpdateOne
from hyperliquid_trader_stats.config import AIOHTTP_PROXY
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_vaults_collection

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# API URL
API_URL = "https://stats-data.hyperliquid.xyz/Mainnet/vaults"

# MongoDB 集合
vaults_collection = web3_hyperliquid_vaults_collection


async def fetch_vaults_data():
    """异步从 Hyperliquid API 获取金库排行榜数据"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, proxy=AIOHTTP_PROXY) as response:
                if response.status != 200:
                    logger.error(f"API 请求失败: HTTP {response.status}")
                    return None

                data = await response.json()
                logger.info(f"成功获取 {len(data)} 条金库数据")
                return data

    except Exception as e:
        logger.error(f"获取金库数据出错: {str(e)}")
        return None


async def store_vaults_to_mongodb(vaults_data):
    """批量将金库数据存储到 MongoDB，支持更新和插入"""
    if not vaults_data:
        logger.warning("无金库数据可存储")
        return

    try:
        # 准备批量操作
        operations = []
        for vault in vaults_data:
            vault_address = vault.get("summary").get("vaultAddress")
            if not vault_address:
                logger.warning("金库数据缺少 vaultAddress，跳过")
                continue

            # 准备存储的数据
            vault_doc = {
                "vaultAddress": vault_address,
                "name": vault.get("summary", {}).get("name"),
                "leader": vault.get("summary", {}).get("leader"),
                "tvl": vault.get("summary", {}).get("tvl"),
                "isClosed": vault.get("summary", {}).get("isClosed"),
                "relationship": vault.get("summary", {}).get("relationship"),
                "createTimeMillis": vault.get("summary", {}).get("createTimeMillis"),
                "pnls": vault.get("pnls"),
                "apr": vault.get("apr"),
                "last_updated": int(time.time()),  # 记录更新时间戳
            }

            # 添加 UpdateOne 操作
            operations.append(
                UpdateOne(
                    {"vaultAddress": vault_address}, {"$set": vault_doc}, upsert=True
                )
            )

        # 执行批量写入
        if operations:
            result = await vaults_collection.bulk_write(operations)
            logger.info(
                f"批量操作完成: 插入 {result.upserted_count} 条, "
                f"更新 {result.modified_count} 条"
            )
        else:
            logger.warning("无有效金库数据需要存储")

    except Exception as e:
        logger.error(f"批量存储金库数据到 MongoDB 出错: {str(e)}")


async def main():
    """主函数：异步获取金库数据并批量存储到 MongoDB"""
    logger.info("开始获取 Hyperliquid 金库排行榜数据")

    # 获取数据
    vaults_data = await fetch_vaults_data()
    if vaults_data:
        # 批量存储到 MongoDB
        await store_vaults_to_mongodb(vaults_data)
        logger.info("金库数据处理完成")
    else:
        logger.error("无法获取金库数据，程序退出")


if __name__ == "__main__":
    asyncio.run(main())
