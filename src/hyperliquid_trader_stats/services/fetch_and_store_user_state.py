import asyncio
import logging

from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_addresses_collection
from hyperliquid_trader_stats.hyper_x_utils import bulk_update_user_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)


async def main(incremental: bool = True):
    # 获取没有 marginSummary 字段的地址
    cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
        # {"effective_position_value": {"$exists": False}}, {"ethAddress": 1}
        {"marginSummary": {"$exists": False}}, {"ethAddress": 1}
    )
    addresses = [doc["ethAddress"] async for doc in cursor if doc["ethAddress"].startswith("0x")]
    logger.info(f"找到 {len(addresses)} 个需要更新的地址")
    if not addresses:
        logger.warning("没有需要更新的地址")
        return
    await bulk_update_user_state(addresses)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logger.info("关闭事件循环")
