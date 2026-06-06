"""
TODO:
应该计算出一张中间表存储已完成交易然后后续来更新或者重置
避免每次重新计算指标的时候多余请求新的历史成交数据

计算每天多少单，每单时间，筛选掉高频量化的地址
"""

import traceback
import aiohttp
from datetime import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from hyperliquid_trader_stats.config import API_URL
from hyperliquid_trader_stats.hyper_x_utils import (
    fetch_user_fills,
    store_fills,
    remove_last_trade_for_coins,
)
import statistics
from pprint import pprint
import asyncio
import logging
import math
from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_user_fills_collection,
    web3_hyperliquid_hyper_x_completed_trades_collection,
)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)


def wilson_lower_bound(wins, total, confidence=0.95):
    if total == 0:
        return 0.0
    z = 1.96  # 95%置信度
    phat = wins / total
    return (
        phat
        + z * z / (2 * total)
        - z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    ) / (1 + z * z / total)


def merge_and_aggregate(fills, open_position_coins: list = None):
    """
    按 币种 + 连续 startPosition=0 分组，使用 Decimal 聚合字段，忽略指定持仓币种的最后一个交易。

    参数：
        fills: list，交易记录列表
        open_position_coins: list，当前持仓的币种列表，忽略这些币种的最后一个交易

    返回：
        list，聚合后的已完成订单列表
    """
    if open_position_coins is None:
        open_position_coins = []

    # 按时间排序
    fills.sort(key=lambda x: x["time"])

    # {} -> {(coin, idx): [fills...]}
    groups = defaultdict(list)
    counters = defaultdict(int)

    # 分组逻辑：遇到 startPosition==0 开启新组
    for f in fills:
        coin = f.get("coin", "UNKNOWN")
        if f.get("startPosition") in ("0", "0.0"):
            counters[coin] += 1
        key = (coin, counters[coin])
        groups[key].append(f)

    aggregated = []
    for (coin, idx), group in groups.items():
        # 忽略空组
        if not group:
            continue

        # 进场和离场交易
        entry_fills = [f for f in group if "Open" in f.get("dir", "")]
        exit_fills = [f for f in group if "Close" in f.get("dir", "")]

        # 最开始进场和离场价格
        first_entry_price = Decimal(entry_fills[0]["px"]) if entry_fills else Decimal(0)
        first_exit_price = Decimal(exit_fills[0]["px"]) if exit_fills else Decimal(0)

        # 进场均价
        entry_weighted_sum = sum(
            Decimal(f["px"]) * Decimal(f["sz"]) for f in entry_fills
        )
        entry_total_size = sum(Decimal(f["sz"]) for f in entry_fills)
        entry_avg_price = (
            (entry_weighted_sum / entry_total_size).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if entry_total_size != 0
            else Decimal(0)
        )

        # 离场均价
        exit_weighted_sum = sum(Decimal(f["px"]) * Decimal(f["sz"]) for f in exit_fills)
        exit_total_size = sum(Decimal(f["sz"]) for f in exit_fills)
        exit_avg_price = (
            (exit_weighted_sum / exit_total_size).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if exit_total_size != 0
            else Decimal(0)
        )

        # 其他聚合字段
        total_size = sum(Decimal(f["sz"]) for f in group) / 2
        total_size = total_size.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_fee = sum(Decimal(f["fee"]) for f in group).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_pnl = sum(Decimal(f["closedPnl"]) for f in group).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net_pnl = (total_pnl - total_fee).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        direction = group[0].get("dir", "")

        # 时间与时长
        start_time = group[0]["time"]
        end_time = group[-1]["time"]
        duration_ms = end_time - start_time
        end_dt = datetime.fromtimestamp(end_time / 1000)
        end_str = end_dt.strftime("%b %d, %I:%M %p")
        seconds = duration_ms / 1000
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        duration_str = f"{hours}h {minutes}m"

        # 计算百分比利润
        invested_capital = entry_avg_price * total_size
        profit_percentage = (
            float(
                (net_pnl / invested_capital * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            if invested_capital != 0
            else 0.0
        )

        # 构造结果
        aggregated.append(
            {
                "coin": coin,
                "coin_index": idx,
                "end_time": end_str,
                "start_time_ms": start_time,
                "end_time_ms": end_time,
                "direction": direction,
                "total_size": float(
                    total_size.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "entry_avg_price": float(
                    entry_avg_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "exit_avg_price": float(
                    exit_avg_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "first_entry_price": (
                    float(
                        first_entry_price.quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                    if entry_fills
                    else 0.0
                ),
                "first_exit_price": (
                    float(
                        first_exit_price.quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                    if exit_fills
                    else 0.0
                ),
                "closed_pnl": float(
                    total_pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "fees": float(
                    total_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "net_pnl": float(
                    net_pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "duration": duration_str,
                "duration_ms": duration_ms,
                "fills_count": len(group),
                "profit_percentage": profit_percentage,
            }
        )

        # 打印调试
        logger.debug(
            f"{coin} {idx} {direction} {end_str} {duration_str} "
            f"Size={total_size:.2f} EntryAvg=${entry_avg_price:.2f} ExitAvg=${exit_avg_price:.2f} "
            f"FirstEntry=${first_entry_price:.2f} FirstExit=${first_exit_price:.2f} "
            f"PnL=${total_pnl:.2f} Fee=${total_fee:.2f} Net=${net_pnl:.2f} "
            f"Fills={len(group)}"
        )

    logger.info(f"🧮 聚合订单数: {len(aggregated)}")
    remove_last_trade_for_coins(aggregated, open_position_coins)

    return aggregated


async def aggregate_user_orders(address: str, open_position_coins: list = None) -> list:
    """
    查询指定地址的交易历史，获取后续成交记录并聚合已完成订单。

    参数：
        address: str，用户地址
        open_position_coins: list，当前持仓的币种列表，忽略这些币种的最后一个交易
        ⚠️ update_fills: bool，是否更新订单. 必须更新订单最新状态，不然忽略目前持仓的时候可能会导致遗漏历史订单

    返回：
        list，聚合后的已完成订单列表
    """
    try:
        # 查询数据库中的历史交易记录
        cursor = web3_hyperliquid_hyper_x_user_fills_collection.find(
            {"ethAddress": address}, {"fill": 1}
        ).batch_size(1000)
        historical_fills = [doc["fill"] async for doc in cursor]
        historical_tid_lst = [_["tid"] for _ in historical_fills]
        logger.info(
            f"📦 地址 {address} 从数据库获取 {len(historical_fills)} 条历史交易记录"
        )

        # 获取最后时间戳
        last_time = max((f["time"] for f in historical_fills), default=0)
        logger.debug(f"⏱️ 地址 {address} 的最后时间戳: {last_time}")

        # 请求 API 获取后续交易记录
        async with aiohttp.ClientSession() as session:
            new_fills = await fetch_user_fills(session, address, start_time=last_time)
            new_fills = [_ for _ in new_fills if _["tid"] not in historical_tid_lst]
            logger.info(f"🌐 地址 {address} 从 API 获取 {len(new_fills)} 条新交易记录")
            await store_fills(address, new_fills)
        # 拼接历史和新记录
        all_fills = historical_fills + new_fills
        logger.info(f"🔗 地址 {address} 总计 {len(all_fills)} 条交易记录")

        if not all_fills:
            logger.warning(f"⚠️ 地址 {address} 无交易记录")
            return []

        # 调用 merge_and_aggregate 聚合订单
        return merge_and_aggregate(all_fills, open_position_coins)

    except Exception as e:
        logger.error(f"❗处理地址 {address} 时发生异常: {e}")
        return []


async def get_user_open_position_coins(address: str) -> list:
    async with aiohttp.ClientSession() as session:
        json_data = {"type": "clearinghouseState", "user": address}
        try:
            async with session.post(API_URL, json=json_data, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return [_["position"]["coin"] for _ in data["assetPositions"]]
                elif response.status == 429:
                    logger.warning(f"获取 {address} 的数据时被限流，睡眠 61 秒")
                    await asyncio.sleep(61)
                    return await get_user_open_position_coins(address)
        except aiohttp.ClientError as e:
            logger.error(f"获取 {address} 的数据时出错: {e}")
            raise Exception(f"获取 {address} 的数据时出错: {e}")


async def compute_complete_trades_and_store(address: str, store=True):
    """
    聚合指定地址的已完成订单并存储到数据库。

    参数：
        address: str，用户地址

    返回：
        None 或其他结果
    """
    open_position_coins = await get_user_open_position_coins(address)  # 持仓币种
    orders = await aggregate_user_orders(address, open_position_coins)

    if not orders:
        logger.warning("⚠️ 处理后未生成任何聚合订单")
        return None
    logger.info(f"地址 {address} 生成了 {len(orders)} 条聚合订单")

    # 计算 completed_trade_pnl
    total_pnl = round(sum(order["closed_pnl"] for order in orders), 2)
    long_pnl = round(
        sum(order["closed_pnl"] for order in orders if "Long" in order["direction"]), 2
    )
    short_pnl = round(
        sum(order["closed_pnl"] for order in orders if "Short" in order["direction"]), 2
    )
    total_fees = round(sum(order["fees"] for order in orders), 2)
    net_pnl = round(total_pnl - total_fees, 2)

    # 计算 duration_stats
    durations_minutes = [order["duration_ms"] / 60000 for order in orders]  # 毫秒转分钟
    if not durations_minutes:
        avg_duration_minutes = 0.0
        median_duration_minutes = 0.0
        q1_duration_minutes = 0.0
        q3_duration_minutes = 0.0
    elif len(durations_minutes) == 1:
        duration = durations_minutes[0]
        avg_duration_minutes = round(duration, 1)
        median_duration_minutes = round(duration, 1)
        q1_duration_minutes = round(duration, 1)  # 单一值作为 q1 和 q3
        q3_duration_minutes = round(duration, 1)
    else:
        avg_duration_minutes = round(statistics.mean(durations_minutes), 1)
        median_duration_minutes = round(statistics.median(durations_minutes), 1)
        q1_duration_minutes = round(
            statistics.quantiles(durations_minutes, n=4)[0], 1
        )  # 25% 分位数
        q3_duration_minutes = round(
            statistics.quantiles(durations_minutes, n=4)[2], 1
        )  # 75% 分位数

    # 计算 stats_per_asset
    stats_per_asset = defaultdict(
        lambda: {"total_pnL": 0, "total_fees": 0, "net_pnl": 0, "number_of_trades": 0}
    )
    for order in orders:
        coin = order["coin"]
        stats_per_asset[coin]["total_pnL"] += order["closed_pnl"]
        stats_per_asset[coin]["total_fees"] += order["fees"]
        stats_per_asset[coin]["net_pnl"] += order["net_pnl"]
        stats_per_asset[coin]["number_of_trades"] += 1

    # 确保 stats_per_asset 中的金额字段保留两位小数
    stats_per_asset = {
        coin: {
            "total_pnL": round(stats["total_pnL"], 2),
            "total_fees": round(stats["total_fees"], 2),
            "net_pnl": round(stats["net_pnl"], 2),
            "number_of_trades": stats["number_of_trades"],
        }
        for coin, stats in stats_per_asset.items()
    }

    # 计算 total_trades, winning_trades, win_rate
    total_trades = len(orders)
    winning_trades = sum(1 for order in orders if order["net_pnl"] > 0)
    win_rate = (
        round((winning_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
    )
    # 综合评分：胜率 * log(交易数+1)
    total_score = (
        round(win_rate * math.log(total_trades + 1), 2) if total_trades > 0 else 0.0
    )
    # Wilson置信区间下界
    total_wilson = (
        round(wilson_lower_bound(winning_trades, total_trades) * 100, 2)
        if total_trades > 0
        else 0.0
    )

    # 计算 win_rate_long 和 win_rate_short
    long_trades = [order for order in orders if "Long" in order["direction"]]
    short_trades = [order for order in orders if "Short" in order["direction"]]
    winning_long_trades = sum(1 for order in long_trades if order["net_pnl"] > 0)
    winning_short_trades = sum(1 for order in short_trades if order["net_pnl"] > 0)
    win_rate_long = (
        round((winning_long_trades / len(long_trades)) * 100, 2) if long_trades else 0.0
    )
    win_rate_short = (
        round((winning_short_trades / len(short_trades)) * 100, 2)
        if short_trades
        else 0.0
    )

    # 计算进场价值区间的订单数量、胜率、综合评分、置信区间下界
    value_thresholds = [1e4, 1e5, 1e6, 1e7]
    entry_value_summary = {}
    for threshold in value_thresholds:
        filtered_orders = [
            order
            for order in orders
            if order["entry_avg_price"] * order["total_size"] >= threshold
        ]
        total = len(filtered_orders)
        win = sum(1 for order in filtered_orders if order["net_pnl"] > 0)
        win_rate_tmp = round((win / total) * 100, 2) if total > 0 else 0.0
        # 综合评分：胜率 * log(交易数+1)
        score = round(win_rate_tmp * math.log(total + 1), 2) if total > 0 else 0.0
        # Wilson置信区间下界
        wilson = round(wilson_lower_bound(win, total) * 100, 2) if total > 0 else 0.0
        # 构造 key，如 win_rate_over_10w
        if threshold >= 1e7:
            key = "win_rate_over_1000w"
        elif threshold >= 1e6:
            key = "win_rate_over_100w"
        elif threshold >= 1e5:
            key = "win_rate_over_10w"
        else:
            key = "win_rate_over_1w"
        entry_value_summary[key] = {
            "total_trades": total,
            "winning_trades": win,
            "win_rate": win_rate_tmp,
            "score": score,
            "wilson_lower_bound": wilson,
        }

    # 构造 data 字典
    data = {
        "ethAddress": address,
        "completed_trades": orders,
        "completed_trade_pnl": {
            "pnl": total_pnl,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "fees": total_fees,
            "net": net_pnl,
        },
        "duration_stats": {
            "avg_duration_minutes": avg_duration_minutes,
            "median_duration_minutes": median_duration_minutes,
            "q1_duration_minutes": q1_duration_minutes,
            "q3_duration_minutes": q3_duration_minutes,
        },
        "stats_per_asset": stats_per_asset,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "win_rate_score": total_score,  # 新增
        "win_rate_wilson_lower_bound": total_wilson,  # 新增
        "win_rate_long": win_rate_long,
        "win_rate_short": win_rate_short,
        "entry_value_summary": entry_value_summary,
        "updated_at": datetime.utcnow(),
    }

    # 存储到数据库 (upsert)
    try:
        result = await web3_hyperliquid_hyper_x_completed_trades_collection.update_one(
            {"ethAddress": address}, {"$set": data}, upsert=True
        )
        if result.matched_count > 0:
            logger.info(f"更新了地址 {address} {len(orders)} 条聚合订单数据聚合的结果")
        else:
            logger.info(f"插入了地址 {address} {len(orders)} 条聚合订单数据聚合的结果")
    except Exception as e:
        logger.error(f"❗存储地址 {address} 的数据到数据库时出错: {e}")
        return None

    logger.info(f"生成 {len(orders)} 条聚合订单")
    return data


async def process_all_addresses_incrementally(
    incremental: bool = True,
):
    """
    从 fills 集合中获取所有唯一地址，根据 incremental 参数决定是否增量处理未在 trades 集合中的地址，
    然后调用 compute_complete_trades_and_store。

    参数：
        incremental: bool，是否增量处理（仅处理 trades 集合中不存在的地址），默认为 True

    返回：
        None
    """
    try:
        # 获取 fills 集合中的所有唯一 ethAddress
        addresses = await web3_hyperliquid_hyper_x_user_fills_collection.distinct(
            "ethAddress"
        )
        logger.info(f"从 fills 集合中获取 {len(addresses)} 个唯一地址")

        # 根据 incremental 参数决定处理的地址列表
        if incremental:
            # 获取 trades 集合中已存在的 ethAddress，且 win_rate_score 字段不存在
            existing_addresses = await web3_hyperliquid_hyper_x_completed_trades_collection.distinct(
                "ethAddress",
                {"win_rate_score": {"$exists": True}}
            )
            logger.info(f"trades 集合中已有 {len(existing_addresses)} 个地址（已存在 win_rate_score 字段）")
            # 过滤出未处理的地址
            addresses_to_process = [
                addr for addr in addresses if addr not in existing_addresses
            ]
            logger.info(f"增量模式：需要处理的地址数: {len(addresses_to_process)}")
        else:
            # 处理所有地址
            addresses_to_process = addresses
            logger.info(f"全量模式：需要处理的地址数: {len(addresses_to_process)}")

        if not addresses_to_process:
            logger.info("✅ 没有需要处理的新地址")
            return

        # 逐个处理地址
        total_count = len(addresses_to_process)
        for idx, address in enumerate(addresses_to_process, 1):
            logger.info(f"🚀 开始处理地址: {address} （进度：{idx}/{total_count}）")
            try:
                result = await compute_complete_trades_and_store(address)
                if result is None:
                    logger.warning(f"❌ 地址 {address} 的聚合订单生成失败")
                else:
                    entry_stats = result.get("entry_value_summary", {})
                    logger.info(
                        f"🎉 地址 {address} 的聚合订单处理完成，{result['total_trades']} 条交易, "
                        f"总胜率 {result['win_rate']}% (评分 {result.get('win_rate_score', '-')}, 下界 {result.get('win_rate_wilson_lower_bound', '-')}) "
                        f"1w: {entry_stats.get('win_rate_over_1w', {}).get('win_rate', '-')}%({entry_stats.get('win_rate_over_1w', {}).get('total_trades', '-')},"
                        f"评分{entry_stats.get('win_rate_over_1w', {}).get('score', '-')},下界{entry_stats.get('win_rate_over_1w', {}).get('wilson_lower_bound', '-')}) "
                        f"10w: {entry_stats.get('win_rate_over_10w', {}).get('win_rate', '-')}%({entry_stats.get('win_rate_over_10w', {}).get('total_trades', '-')},"
                        f"评分{entry_stats.get('win_rate_over_10w', {}).get('score', '-')},下界{entry_stats.get('win_rate_over_10w', {}).get('wilson_lower_bound', '-')}) "
                        f"100w: {entry_stats.get('win_rate_over_100w', {}).get('win_rate', '-')}%({entry_stats.get('win_rate_over_100w', {}).get('total_trades', '-')},"
                        f"评分{entry_stats.get('win_rate_over_100w', {}).get('score', '-')},下界{entry_stats.get('win_rate_over_100w', {}).get('wilson_lower_bound', '-')}) "
                        f"1000w: {entry_stats.get('win_rate_over_1000w', {}).get('win_rate', '-')}%({entry_stats.get('win_rate_over_1000w', {}).get('total_trades', '-')},"
                        f"评分{entry_stats.get('win_rate_over_1000w', {}).get('score', '-')},下界{entry_stats.get('win_rate_over_1000w', {}).get('wilson_lower_bound', '-')})"
                    )
            except Exception as e:
                logger.error(f"💥 处理地址 {address} 时发生错误: {e}")
                traceback.print_exc()
                continue

    except Exception as e:
        logger.error(f"处理地址列表时发生异常: {e}")


async def main():
    """
    测试函数：运行增量和全量处理。
    """
    try:
        # 测试增量处理
        logger.info("开始增量处理测试")
        await process_all_addresses_incrementally(incremental=True)

        # 可选：测试全量处理
        # logger.info("开始全量处理测试")
        # await process_all_addresses_incrementally(incremental=False)
    finally:
        logger.info("关闭事件循环")


if __name__ == "__main__":
    asyncio.run(main())
