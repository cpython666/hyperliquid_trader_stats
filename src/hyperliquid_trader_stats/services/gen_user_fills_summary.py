import asyncio
import logging
from datetime import datetime
from hyperliquid_trader_stats.db.collections import (web3_hyperliquid_hyper_x_user_fills_collection,
                web3_hyperliquid_hyper_x_user_fills_summary_collection)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")]
)
logger = logging.getLogger(__name__)


async def initialize_redundant_table():
    """
    初始化冗余表，删除现有数据并重新插入每个地址的最新交易时间和当前更新时间。
    """
    try:
        logger.info("开始初始化冗余表...")

        # 聚合每个地址的最新时间
        pipeline = [
            {"$group": {
                "_id": "$ethAddress",
                "lastTime": {"$max": "$time"}
            }}
        ]
        cursor = web3_hyperliquid_hyper_x_user_fills_collection.aggregate(pipeline)

        # 准备插入冗余表的数据，添加更新时间
        now = datetime.utcnow()
        documents = [
            {"ethAddress": doc["_id"], "lastTime": doc["lastTime"], "updatedAt": now}
            async for doc in cursor
        ]
        logger.info(f"找到 {len(documents)} 个地址的最新时间。")

        if not documents:
            logger.info("没有数据需要插入冗余表。")
            return

        # 删除现有数据并插入新数据
        await web3_hyperliquid_hyper_x_user_fills_summary_collection.delete_many({})
        await web3_hyperliquid_hyper_x_user_fills_summary_collection.insert_many(documents)
        logger.info(f"冗余表初始化完成，插入了 {len(documents)} 条记录。")

    except Exception as e:
        logger.error(f"初始化冗余表失败: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(initialize_redundant_table())
    finally:
        logger.info("脚本执行完成。")