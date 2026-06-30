import asyncio
import logging
from datetime import datetime
from typing import Optional

from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_addresses_collection
from hyperliquid_trader_stats.hyper_x_utils import bulk_update_user_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)


def _build_user_state_query(
    incremental: bool = True,
    updated_before: Optional[datetime] = None,
) -> dict:
    """根据采集模式构建地址查询条件。"""
    if not incremental and updated_before is not None:
        raise ValueError("全量模式不能与更新时间筛选同时使用")

    query = {"ethAddress": {"$regex": "^0x"}}
    if updated_before is not None:
        query["$or"] = [
            {"updated_at": {"$lte": updated_before}},
            {"updated_at": {"$exists": False}},
        ]
    elif incremental:
        query["marginSummary"] = {"$exists": False}
    return query


async def main(
    incremental: bool = True,
    updated_before: Optional[datetime] = None,
):
    """按增量、全量或更新时间筛选地址，并批量刷新持仓状态。"""
    query = _build_user_state_query(
        incremental=incremental,
        updated_before=updated_before,
    )
    cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
        query,
        {"ethAddress": 1},
    )
    addresses = [doc["ethAddress"] async for doc in cursor]

    if not incremental:
        mode = "全量模式"
    elif updated_before is not None:
        mode = f"过期刷新模式（截止 {updated_before} UTC）"
    else:
        mode = "增量模式"
    logger.info("%s：找到 %s 个需要更新的地址", mode, len(addresses))

    if not addresses:
        logger.warning("没有需要更新的地址")
        return
    await bulk_update_user_state(addresses)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logger.info("关闭事件循环")
