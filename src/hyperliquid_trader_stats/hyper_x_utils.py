import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Union

import aiohttp
from datetime import datetime
from pymongo import UpdateOne
from hyperliquid_trader_stats.config import API_URL
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_user_fills_collection, web3_hyperliquid_hyper_x_addresses_collection, \
    web3_hyperliquid_hyper_x_user_fills_summary_collection

# 配置日志
logging.basicConfig(
    # level=logging.DEBUG,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")]
)
logger = logging.getLogger(__name__)

# API 端点和请求头
BASE_URL = "https://api-ui.hyperliquid.xyz/info"
HEADERS = {"Content-Type": "application/json"}


async def fetch_user_state(session: aiohttp.ClientSession, address: str, retries=3, timeout=10):
    """请求单个地址的 clearinghouseState，并按限流/异常策略重试。"""
    json_data = {"type": "clearinghouseState", "user": address}
    for attempt in range(retries):
        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with session.post(API_URL, headers=HEADERS, json=json_data,
                                    timeout=client_timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"获取到地址 {address} 的状态: {data}")
                    return data
                elif response.status == 429:
                    logger.warning(f"地址 {address} 请求限流，睡眠 61 秒")
                    await asyncio.sleep(61)
                else:
                    logger.warning(f"地址 {address} 第 {attempt + 1} 次请求失败，状态码: {response.status}")
        except Exception as e:
            logger.warning(f"地址 {address} 第 {attempt + 1} 次请求异常: {e}")
        await asyncio.sleep(2)
    logger.error(f"获取地址 {address} 的状态失败")
    return None


async def save_addresses(addresses: Union[list, set], source="hyperliquid_leaderboard"):
    """将一批地址按来源批量 upsert 到地址集合。"""
    if not addresses:
        logger.warning("地址数据为空")
        return
    operations = []
    now = datetime.utcnow()

    for idx, address in enumerate(addresses, 1):
        operations.append(
            UpdateOne(
                {"ethAddress": address},
                {
                    "$set": {
                        "ethAddress": address,
                        "source": source,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True
            )
        )
        if idx % 1000 == 0:
            logger.info(f"已处理 {idx} 条地址...")

    if operations:
        logger.info(f"准备批量写入 {len(operations)} 条操作")
        batch_size = 1000
        for i in range(0, len(operations), batch_size):
            batch = operations[i:i + batch_size]
            try:
                result = await web3_hyperliquid_hyper_x_addresses_collection.bulk_write(batch, ordered=False)
                logger.info(
                    f"批次 {i // batch_size + 1} 写入完成：插入 {result.upserted_count} 条，更新 {result.modified_count} 条"
                )
            except Exception as e:
                logger.error(f"批次 {i // batch_size + 1} 写入失败: {e}")
    else:
        logger.warning("无有效地址进行写入")


def convert_to_float(data: dict) -> dict:
    """将 marginSummary、crossMarginSummary、withdrawable 和 assetPositions.position 的字段转换为浮点数"""
    if not data:
        return data
    processed = data.copy()
    for key in ["marginSummary", "crossMarginSummary"]:
        if key in processed and isinstance(processed[key], dict):
            for sub_key, value in processed[key].items():
                try:
                    processed[key][sub_key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"无法转换 {key}.{sub_key} 的值 {value} 为浮点数")
    if "withdrawable" in processed:
        try:
            processed["withdrawable"] = float(processed["withdrawable"])
        except (ValueError, TypeError):
            logger.warning(f"无法转换 withdrawable 的值 {processed['withdrawable']} 为浮点数")
    return processed


async def bulk_update_user_state(addresses: list, batch_size=100):
    """
    批量更新用户状态信息，计算仓位有效价值并存储到 addresses 集合。

    参数：
        addresses: list，要更新的地址列表
        batch_size: int，每批处理的地址数量，默认为 100
        collection: AsyncIOMotorCollection，目标集合 (web3_hyperliquid_hyper_x_addresses_collection)

    返回：
        None
    """
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(addresses), batch_size):
            batch_addresses = addresses[i:i + batch_size]
            logger.info(f"处理批次 {i // batch_size + 1}，包含 {len(batch_addresses)} 个地址")

            operations = []
            now = datetime.utcnow()

            for address in batch_addresses:
                if address == "Leader":
                    continue
                try:
                    state = await fetch_user_state(session, address)
                    if not state:
                        logger.warning(f"地址 {address} 未获取到状态信息")
                        continue

                    processed_state = convert_to_float(state)

                    # 计算仓位有效价值
                    effective_position_value = Decimal("0")
                    if "assetPositions" in state and isinstance(state["assetPositions"], list):
                        for pos in state["assetPositions"]:
                            if "position" in pos and isinstance(pos["position"], dict):
                                position_value = pos["position"].get("positionValue")
                                szi = pos["position"].get("szi")
                                if position_value is not None and szi is not None:
                                    try:
                                        position_value = Decimal(position_value)
                                        szi = Decimal(szi)
                                        # 根据 szi 正负调整 positionValue
                                        signed_position_value = position_value if szi >= 0 else -position_value
                                        effective_position_value += signed_position_value
                                    except (ValueError, TypeError) as e:
                                        logger.warning(f"地址 {address} 的 positionValue 或 szi 转换失败: {e}")
                        # 保留三位小数
                    effective_position_value = float(
                        effective_position_value.quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)
                    )

                    operations.append(
                        UpdateOne(
                            {"ethAddress": address},
                            {
                                "$set": {
                                    "state": state,
                                    "marginSummary": processed_state.get("marginSummary"),
                                    "crossMarginSummary": processed_state.get("crossMarginSummary"),
                                    "withdrawable": processed_state.get("withdrawable"),
                                    "effective_position_value": effective_position_value,
                                    "updated_at": now
                                },
                                "$setOnInsert": {"createdAt": now}
                            },
                            upsert=True
                        )
                    )
                    logger.debug(f"地址 {address} 的仓位有效价值: {effective_position_value}")

                except Exception as e:
                    logger.error(f"处理地址 {address} 时发生错误: {e}")
                    continue

            if operations:
                try:
                    result = await web3_hyperliquid_hyper_x_addresses_collection.bulk_write(operations, ordered=False)
                    logger.info(
                        f"批次 {i // batch_size + 1} 写入完成：插入 {result.upserted_count} 条，更新 {result.modified_count} 条"
                    )
                except Exception as e:
                    logger.error(f"批次 {i // batch_size + 1} 写入失败: {e}")
            else:
                logger.warning(f"批次 {i // batch_size + 1} 无有效状态数据")


async def fetch_user_fills(session: aiohttp.ClientSession, address: str, start_time: int = 0, retries=3,
                           timeout=10) -> list:
    """
    分页获取用户的交易历史（userFills），支持增量采集，保留原始数据。

    参数：
        session: aiohttp.ClientSession，异步 HTTP 客户端会话
        address: str，用户を守
        start_time: int，起始时间戳（毫秒），用于增量采集
        retries: int，最大重试次数
        timeout: int，单次请求超时时间（秒）

    返回：
        list，包含所有去重后的交易记录
    """
    all_fills = []
    seen_tids = set()
    current_start_time = start_time

    while True:
        payload = {
            "aggregateByTime": True,
            "startTime": current_start_time,
            "type": "userFillsByTime",
            "user": address
        }
        logger.debug(f"获取地址 {address} 的交易记录，起始时间: {current_start_time}")

        for attempt in range(retries):
            try:
                client_timeout = aiohttp.ClientTimeout(total=timeout)
                async with session.post(BASE_URL, headers=HEADERS, json=payload, timeout=client_timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        fills = data.get("fills", []) if isinstance(data, dict) else data
                        new_fills = []

                        # 去重并过滤无效记录
                        for f in fills:
                            tid = f.get("tid")
                            if tid not in seen_tids:
                                seen_tids.add(tid)
                                new_fills.append(f)

                        all_fills.extend(new_fills)
                        logger.debug(f"地址 {address} 本页获取 {len(new_fills)} 条新记录，总计 {len(all_fills)} 条")

                        # 如果本页数据少于阈值，结束分页
                        if len(fills) < 2000:
                            return all_fills

                        # 更新下一页的起始时间
                        current_start_time = fills[-1]["time"]
                        break
                    elif response.status == 429:
                        logger.warning(f"地址 {address} 请求限流，睡眠 61 秒")
                        await asyncio.sleep(61)
                    else:
                        logger.warning(f"地址 {address} 第 {attempt + 1} 次请求失败，状态码: {response.status}")
            except Exception as e:
                logger.warning(f"地址 {address} 第 {attempt + 1} 次请求异常: {e}")
            await asyncio.sleep(2)
        else:
            logger.error(f"地址 {address} 获取交易记录失败")
            break

    return all_fills


async def store_fills(address: str, fills: list):
    """
    存储用户交易记录到 MongoDB，并更新冗余表中的最新时间和更新时间。

    参数：
        address: str，用户地址
        fills: list，交易记录列表，每个记录包含 tid, coin, time 等字段
    """
    operations = []
    now = datetime.utcnow()

    if not fills:
        logger.warning(f"地址 {address} 无有效交易记录")
        return

    try:
        # 准备批量写入的操作
        for fill in fills:
            tid = fill.get("tid")
            if not tid:  # 确保 tid 存在
                logger.warning(f"地址 {address} 的交易记录缺少 tid: {fill}")
                continue
            operations.append(
                UpdateOne(
                    {"ethAddress": address, "tid": tid},
                    {
                        "$set": {
                            "ethAddress": address,
                            "tid": tid,
                            "fill": fill,
                            "coin": fill.get("coin"),
                            "time": fill.get("time"),
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True
                )
            )

        if not operations:
            logger.warning(f"地址 {address} 所有交易记录无效")
            return

        # 批量写入交易记录
        result = await web3_hyperliquid_hyper_x_user_fills_collection.bulk_write(operations, ordered=False)
        logger.info(
            f"地址 {address} 写入完成：插入 {result.upserted_count} 条，更新 {result.modified_count} 条"
        )

        # 获取最新时间并更新冗余表
        latest_time = max(fill["time"] for fill in fills if fill.get("time"))
        await web3_hyperliquid_hyper_x_user_fills_summary_collection.update_one(
            {"ethAddress": address},
            {
                "$set": {
                    "lastTime": latest_time,
                    "updatedAt": now  # 添加更新时间
                }
            },
            upsert=True
        )
        logger.info(f"地址 {address} 冗余表更新，最新时间: {latest_time}, 更新时间: {now}")

    except Exception as e:
        logger.error(f"地址 {address} 处理交易记录失败: {e}")
        raise


def remove_last_trade_for_coins(completed_trades: list, coins: list[str]) -> None:
    """
    从 fills（按时间升序）中删除每个 coin 的最后一笔交易。

    参数：
        fills (list): 交易记录列表，必须已按时间升序排列。
        coins (list[str]): 要处理的币种名列表，例如 ["ETH", "BTC"]
    """
    # 记录每个币种的最后一笔交易的索引
    last_indices = {}
    for i in range(len(completed_trades) - 1, -1, -1):
        coin = completed_trades[i].get("coin")
        if coin in coins and coin not in last_indices:
            last_indices[coin] = i
        if len(last_indices) == len(coins):
            break  # 所有目标币种都找到了

    # 删除对应索引（从大到小删除避免索引错位）
    for index in sorted(last_indices.values(), reverse=True):
        del completed_trades[index]


async def main():
    """
    主函数：获取所有地址，分页获取并存储用户的交易历史。
    """
    # 获取所有地址
    addresses = ['0xcb92c5988b1d4f145a7b481690051f03ead23a13']
    await bulk_update_user_state(addresses)


if __name__ == "__main__":
    # fills = [
    #     {"coin": "BTC", "time": 1000},
    #     {"coin": "ETH", "time": 2000},
    #     {"coin": "BTC", "time": 3000},
    #     {"coin": "ETH", "time": 4000},
    #     {"coin": "DOGE", "time": 5000},
    # ]
    #
    # remove_last_trade_for_coins(fills, ["ETH", "BTC"])
    # print(fills)
    asyncio.run(main())
