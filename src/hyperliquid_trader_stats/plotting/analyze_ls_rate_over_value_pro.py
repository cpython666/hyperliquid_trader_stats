import asyncio
import logging
import os
from datetime import datetime
from pprint import pprint
from time import perf_counter
import matplotlib.pyplot as plt
import seaborn as sns
from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_addresses_collection,
    web3_hyperliquid_hyper_x_completed_trades_collection,
    web3_hyperliquid_hyper_x_analyze_result_collection,
)

# 设置全局字体为支持中文的字体
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS"]  # 通用字体
plt.rcParams["axes.unicode_minus"] = False  # 解决负号问题

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

VALUE_KEYS = [
    "win_rate_over_1w",
    "win_rate_over_10w",
    "win_rate_over_100w",
    "win_rate_over_1000w",
]
WINRATE_THRESHOLDS = [50, 60, 70, 80, 90]
VALUE_WINRATE_THRESHOLDS = [50, 60, 70, 80, 90, 100]
POSITION_KEYS = ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]


def _empty_distribution(keys):
    return {
        key: {
            **_empty_position_item(),
        }
        for key in keys
    }


def _empty_position_item():
    return {
        "long": 0,
        "short": 0,
        "long_value_sum": 0.0,
        "short_value_sum": 0.0,
        "ratio": None,
        "value_ratio": None,
    }


def _add_position_item(item: dict, pos_value: float):
    if pos_value > 0:
        item["long"] += 1
        item["long_value_sum"] += pos_value
    elif pos_value < 0:
        item["short"] += 1
        item["short_value_sum"] += pos_value


def _add_position(distribution: dict, key: str, pos_value: float):
    _add_position_item(distribution[key], pos_value)


def _finalize_distribution(distribution: dict):
    for item in distribution.values():
        long_count = item["long"]
        short_count = item["short"]
        long_value = item["long_value_sum"]
        short_value = item["short_value_sum"]
        item["ratio"] = round(long_count / short_count, 2) if short_count > 0 else None
        item["value_ratio"] = (
            round(long_value / abs(short_value), 2) if abs(short_value) > 0 else None
        )
        item["long_value_sum"] = round(long_value, 3)
        item["short_value_sum"] = round(short_value, 3)


async def _estimated_count(collection, label: str) -> int:
    try:
        return await collection.estimated_document_count()
    except Exception as error:
        logger.warning("%s 快速计数失败，回退到精确计数: %s", label, error)
        return await collection.count_documents({})


def _log_elapsed(started_at: float, label: str) -> float:
    now = perf_counter()
    logger.info("%s耗时: %.2f 秒", label, now - started_at)
    return now


async def analyze_winrate_and_positions():
    """
    统计地址总数、已分析交易地址数、胜率分布及多空仓位分布。

    参数：
        addresses_collection (AsyncIOMotorCollection): 存储地址数据的 MongoDB 集合，默认为 web3_hyperliquid_hyper_x_addresses_collection。
        trades_collection (AsyncIOMotorCollection): 存储交易数据的 MongoDB 集合，默认为 web3_hyperliquid_hyper_x_completed_trades_collection。

    返回：
        dict: 包含以下统计结果的字典：
            - total_addresses (int): 总地址数。
            - analyzed_addresses (int): 已分析交易的地址数。
            - winrate_distribution (dict): 各胜率阈值（>=50%、>=60%、>=70%、>=80%、>=90%）的地址数量。
            - position_distribution (dict): 各胜率阈值（>=50、>=60、>=70、>=80、>=90、=100）的多空仓位分布，包括：
                - long (int): 多头地址数量。
                - short (int): 空头地址数量。
                - long_value_sum (float): 多头仓位有效价值总和。
                - short_value_sum (float): 空头仓位有效价值总和。
                - ratio (float 或 None): 多空地址数量比值（long/short，若 short > 0 则计算，否则为 None）。
                - value_ratio (float 或 None): 多空仓位价值总和比值（long_value_sum/short_value_sum，若 short_value_sum > 0 则计算，否则为 None）。

    异常：
        如果发生异常（如数据库连接失败），记录错误日志并返回空字典 {}。
    """
    try:
        started_at = perf_counter()
        step_started_at = started_at

        total_addresses, estimated_analyzed_addresses = await asyncio.gather(
            _estimated_count(web3_hyperliquid_hyper_x_addresses_collection, "总地址数"),
            _estimated_count(
                web3_hyperliquid_hyper_x_completed_trades_collection,
                "已分析交易地址数",
            )
        )
        logger.info(f"总地址数: {total_addresses}")
        logger.info(f"已分析交易的地址数（估算）: {estimated_analyzed_addresses}")
        step_started_at = _log_elapsed(step_started_at, "地址计数")

        addresses_cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
            {"effective_position_value": {"$exists": True, "$ne": None}},
            {"ethAddress": 1, "effective_position_value": 1},
        ).batch_size(5000)
        addresses_data = {}
        async for doc in addresses_cursor:
            addresses_data[doc["ethAddress"]] = doc["effective_position_value"]
            if len(addresses_data) % 10000 == 0:
                logger.info("已读取 %s 个地址的仓位数据", len(addresses_data))
        logger.info(f"获取到 {len(addresses_data)} 个地址的仓位数据")
        step_started_at = _log_elapsed(step_started_at, "读取仓位数据")

        winrate_distribution = {f"ge_{thresh}": 0 for thresh in WINRATE_THRESHOLDS}
        position_distribution = _empty_distribution(POSITION_KEYS)
        value_position_distribution = {
            key: {
                f"ge_{thresh}": _empty_position_item()
                for thresh in VALUE_WINRATE_THRESHOLDS
            }
            for key in VALUE_KEYS
        }
        projection = {"ethAddress": 1, "win_rate": 1}
        for key in VALUE_KEYS:
            projection[f"entry_value_summary.{key}.win_rate"] = 1

        trades_cursor = web3_hyperliquid_hyper_x_completed_trades_collection.find(
            {
                "$or": [
                    {"win_rate": {"$exists": True, "$ne": None}},
                    {"entry_value_summary": {"$exists": True, "$ne": None}},
                ]
            },
            projection,
        ).batch_size(5000)

        winrate_data_count = 0
        entry_value_data_count = 0

        async for doc in trades_cursor:
            addr = doc.get("ethAddress")
            pos_value = addresses_data.get(addr)

            win_rate = doc.get("win_rate")
            if win_rate is not None:
                winrate_data_count += 1
                for thresh in WINRATE_THRESHOLDS:
                    if win_rate >= thresh:
                        winrate_distribution[f"ge_{thresh}"] += 1

                if pos_value is not None:
                    for thresh in WINRATE_THRESHOLDS:
                        if win_rate >= thresh:
                            _add_position(
                                position_distribution, f"ge_{thresh}", pos_value
                            )
                    if win_rate == 100:
                        _add_position(position_distribution, "eq_100", pos_value)

            entry_summary = doc.get("entry_value_summary")
            if not entry_summary:
                continue

            entry_value_data_count += 1
            if entry_value_data_count % 10000 == 0:
                logger.info(
                    "已统计 %s 个交易地址，包含 %s 个 entry_value_summary",
                    winrate_data_count,
                    entry_value_data_count,
                )
            if pos_value is None:
                continue

            for key in VALUE_KEYS:
                win_rate = entry_summary.get(key, {}).get("win_rate", 0)
                for thresh in VALUE_WINRATE_THRESHOLDS:
                    if win_rate >= thresh:
                        _add_position_item(
                            value_position_distribution[key][f"ge_{thresh}"], pos_value
                        )

        logger.info(f"获取并统计 {winrate_data_count} 个地址的胜率数据")
        logger.info(
            f"获取并统计 {entry_value_data_count} 个地址的 entry_value_summary 数据"
        )
        analyzed_addresses = winrate_data_count
        logger.info(f"已分析交易的地址数（精确）: {analyzed_addresses}")
        step_started_at = _log_elapsed(step_started_at, "读取并统计交易数据")

        _finalize_distribution(position_distribution)
        for key in value_position_distribution:
            _finalize_distribution(value_position_distribution[key])

        logger.info(f"胜率分布: {winrate_distribution}")
        logger.info(f"多空分布: {position_distribution}")
        logger.info(
            f"各仓位价值区间各胜率阈值的多空分布: {value_position_distribution}"
        )

        # 合并结果
        result = {
            "total_addresses": total_addresses,
            "analyzed_addresses": analyzed_addresses,
            "winrate_distribution": winrate_distribution,
            "position_distribution": position_distribution,
            "value_position_distribution": value_position_distribution,  # 新增
            "timestamp": datetime.utcnow(),  # 添加时间戳
        }
        _log_elapsed(started_at, "分析总")
        return result

    except Exception as e:
        logger.error(f"分析失败: {e}")
        return {}


def visualize_with_seaborn(result: dict, output_dir: str = "./plots_tmp"):
    """将按入场价值分层后的胜率和多空分布绘制为汇总图。"""
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        import numpy as np

        os.makedirs(output_dir, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")

        rate_labels = ["≥50", "≥60", "≥70", "≥80", "≥90", "=100"]
        longs = [result["position_distribution"][k]["long"] for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        shorts = [result["position_distribution"][k]["short"] for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        long_vals = [result["position_distribution"][k]["long_value_sum"] for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        short_vals = [abs(result["position_distribution"][k]["short_value_sum"]) for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        value_ratio = [result["position_distribution"][k]["value_ratio"] if result["position_distribution"][k]["value_ratio"] is not None else 0 for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        ratio = [result["position_distribution"][k]["ratio"] if result["position_distribution"][k]["ratio"] is not None else 0 for k in ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]]
        win_counts = [
            result["winrate_distribution"]["ge_50"],
            result["winrate_distribution"]["ge_60"],
            result["winrate_distribution"]["ge_70"],
            result["winrate_distribution"]["ge_80"],
            result["winrate_distribution"]["ge_90"],
            0,
        ]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # 1. 胜率分布柱状图
        sns.barplot(x=rate_labels[:-1], y=win_counts[:-1], ax=axes[0, 0])
        axes[0, 0].set_xlabel("胜率阈值 (%)")
        axes[0, 0].set_ylabel("地址数量")
        axes[0, 0].set_title("胜率分布")

        # 2. 多空仓位数量分布分组柱状图
        x = np.arange(len(rate_labels))
        width = 0.35
        axes[0, 1].bar(x - width / 2, longs, width=width, label="多头")
        axes[0, 1].bar(x + width / 2, shorts, width=width, label="空头")
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(rate_labels)
        axes[0, 1].set_xlabel("胜率阈值 (%)")
        axes[0, 1].set_ylabel("地址数量")
        axes[0, 1].set_title("多空仓位数量分布")
        axes[0, 1].legend()

        # 3. 多空数量比值折线图
        sns.lineplot(x=rate_labels, y=ratio, marker="o", ax=axes[1, 0])
        axes[1, 0].set_xlabel("胜率阈值 (%)")
        axes[1, 0].set_ylabel("多空数量比值 (long/short)")
        axes[1, 0].set_title("多空数量比值分布")

        # 4. 多空价值比值折线图
        sns.lineplot(x=rate_labels, y=value_ratio, marker="o", ax=axes[1, 1])
        axes[1, 1].set_xlabel("胜率阈值 (%)")
        axes[1, 1].set_ylabel("多空价值比值 (long/short)")
        axes[1, 1].set_title("多空价值比值分布")

        plt.tight_layout()
        plt.savefig(f"{output_dir}/all_in_one_{now}.png")
        plt.show()
        plt.close()

        logger.info(f"合并图表已保存到 {output_dir}/all_in_one_{now}.png")

    except Exception as e:
        logger.error(f"可视化失败: {e}")


async def store_analysis_result(result: dict):
    """
    将分析结果存储到 MongoDB 集合。

    参数：
        result (dict): 包含分析结果的字典。

    返回：
        None: 结果存储成功后返回 None。
    """
    try:
        if result:
            await web3_hyperliquid_hyper_x_analyze_result_collection.insert_one(result)
            logger.info(f"分析结果已存储，时间戳: {result['timestamp']}")
        else:
            logger.warning("无分析结果可存储")
    except Exception as e:
        logger.error(f"存储分析结果失败: {e}")
        raise


async def analyze_ls_rate(store_result: bool = True, visualize_result: bool = False):
    """
    主函数，运行分析并可视化。

    异常：
        如果发生异常（如分析或可视化失败），记录错误日志。
    """
    try:
        result = await analyze_winrate_and_positions()
        logger.info(f"分析结果: {result}")
        pprint(result)
        if result and store_result:
            await store_analysis_result(result)
        if result and visualize_result:
            visualize_with_seaborn(result)
    except Exception as e:
        logger.error(f"主函数异常: {e}")
    finally:
        logger.info("关闭事件循环")


if __name__ == "__main__":
    asyncio.run(analyze_ls_rate(store_result=False, visualize_result=True))
