import asyncio
from datetime import datetime, timedelta
import logging
from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_completed_trades_collection,
    web3_hyperliquid_hyper_x_addresses_collection
)
from hyperliquid_trader_stats.hyper_x_utils import bulk_update_user_state

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log", encoding="utf-8")]
)
logger = logging.getLogger(__name__)


async def update_high_winrate_positions(
        win_rate_threshold: int = 50,
        update_interval_minutes: int = 60,
):
    """
    1) 从 completed_trades 筛出 win_rate >= 阈值 的地址列表
    2) 在 addresses 表里再次筛选 updatedAt <= interval_ago 或者不存在 updatedAt
    3) 对最终地址列表调用 bulk_update_user_state
    """
    # 计算时间阈值
    interval_ago = datetime.utcnow() - timedelta(minutes=update_interval_minutes)
    logger.info(f"⏳ 阈值：win_rate >= {win_rate_threshold}，updated_at <= {interval_ago}")

    # 第一步：查询所有胜率满足的地址（去重）
    cursor1 = web3_hyperliquid_hyper_x_completed_trades_collection.find(
        {
            "$or": [
                {"win_rate": {"$gte": win_rate_threshold}},
                {"entry_value_summary.win_rate_over_1w.win_rate": {"$gte": win_rate_threshold}},
                {"entry_value_summary.win_rate_over_10w.win_rate": {"$gte": win_rate_threshold}},
                {"entry_value_summary.win_rate_over_100w.win_rate": {"$gte": win_rate_threshold}},
                {"entry_value_summary.win_rate_over_1000w.win_rate": {"$gte": win_rate_threshold}},
            ]
        },
        {"ethAddress": 1}
    )
    # 用 set 去重
    win_addresses = {doc["ethAddress"] async for doc in cursor1}
    logger.info(f"🏆 第1步：共找到 {len(win_addresses)} 个总胜率或任一区间胜率 >= {win_rate_threshold} 的地址")

    if not win_addresses:
        logger.warning("⚠️ 没有任何地址满足胜率阈值，退出。")
        return

    # 第二步：在 addresses 表里进一步按时间筛选
    cursor2 = web3_hyperliquid_hyper_x_addresses_collection.find(
        {
            "ethAddress": {"$in": list(win_addresses)},
            "$or": [
                {"updated_at": {"$lte": interval_ago}},
                {"updated_at": {"$exists": False}}
            ]
        },
        {"ethAddress": 1}
    )
    addresses = [doc["ethAddress"] async for doc in cursor2]
    logger.info(f"🔄 第2步：在地址表中，有 {len(addresses)} 个地址需要更新")

    if not addresses:
        logger.info("✅ 地址表中无需要更新的数据，退出。")
        return
    await bulk_update_user_state(addresses)


async def main():
    try:
        await update_high_winrate_positions(
            # win_rate_threshold=50,
            # update_interval_minutes=30
        )
    except Exception as e:
        logger.exception(f"💥 主流程异常：{e}")


if __name__ == "__main__":
    asyncio.run(main())
    logger.info("🎉 脚本执行完毕。")
