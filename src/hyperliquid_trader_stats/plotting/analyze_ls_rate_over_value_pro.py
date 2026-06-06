import asyncio
import logging
import os
from datetime import datetime
from pprint import pprint
import matplotlib.pyplot as plt
import seaborn as sns
from motor.motor_asyncio import AsyncIOMotorCollection
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
        # 统计总地址数
        total_addresses = (
            await web3_hyperliquid_hyper_x_addresses_collection.count_documents({})
        )
        logger.info(f"总地址数: {total_addresses}")

        # 统计已分析交易的地址数
        analyzed_addresses = (
            await web3_hyperliquid_hyper_x_completed_trades_collection.count_documents(
                {}
            )
        )
        logger.info(f"已分析交易的地址数: {analyzed_addresses}")

        # 获取胜率数据
        trades_cursor = web3_hyperliquid_hyper_x_completed_trades_collection.find(
            {"win_rate": {"$exists": True, "$ne": None}},
            {"ethAddress": 1, "win_rate": 1},
        )
        trades_data = {
            doc["ethAddress"]: doc["win_rate"] async for doc in trades_cursor
        }
        logger.info(f"获取到 {len(trades_data)} 个地址的胜率数据")

        # 获取仓位数据
        addresses_cursor = web3_hyperliquid_hyper_x_addresses_collection.find(
            {"effective_position_value": {"$exists": True, "$ne": None}},
            {"ethAddress": 1, "effective_position_value": 1},
        )
        addresses_data = {
            doc["ethAddress"]: doc["effective_position_value"]
            async for doc in addresses_cursor
        }
        logger.info(f"获取到 {len(addresses_data)} 个地址的仓位数据")

        # 胜率分布（>= 50%、>= 60%、>= 70%、>= 80%、>= 90%）
        winrate_distribution = {
            "ge_50": sum(1 for win_rate in trades_data.values() if win_rate >= 50),
            "ge_60": sum(1 for win_rate in trades_data.values() if win_rate >= 60),
            "ge_70": sum(1 for win_rate in trades_data.values() if win_rate >= 70),
            "ge_80": sum(1 for win_rate in trades_data.values() if win_rate >= 80),
            "ge_90": sum(1 for win_rate in trades_data.values() if win_rate >= 90),
        }
        logger.info(f"胜率分布: {winrate_distribution}")

        # 多空分布，包含数量、价值总和及比值
        position_distribution = {
            "ge_50": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
            "ge_60": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
            "ge_70": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
            "ge_80": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
            "ge_90": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
            "eq_100": {
                "long": 0,
                "short": 0,
                "long_value_sum": 0.0,
                "short_value_sum": 0.0,
                "ratio": None,
                "value_ratio": None,
            },
        }

        for addr, win_rate in trades_data.items():
            if addr not in addresses_data:
                continue
            pos_value = addresses_data[addr]
            if win_rate >= 50:
                if pos_value > 0:
                    position_distribution["ge_50"]["long"] += 1
                    position_distribution["ge_50"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["ge_50"]["short"] += 1
                    position_distribution["ge_50"]["short_value_sum"] += pos_value
            if win_rate >= 60:
                if pos_value > 0:
                    position_distribution["ge_60"]["long"] += 1
                    position_distribution["ge_60"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["ge_60"]["short"] += 1
                    position_distribution["ge_60"]["short_value_sum"] += pos_value
            if win_rate >= 70:
                if pos_value > 0:
                    position_distribution["ge_70"]["long"] += 1
                    position_distribution["ge_70"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["ge_70"]["short"] += 1
                    position_distribution["ge_70"]["short_value_sum"] += pos_value
            if win_rate >= 80:
                if pos_value > 0:
                    position_distribution["ge_80"]["long"] += 1
                    position_distribution["ge_80"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["ge_80"]["short"] += 1
                    position_distribution["ge_80"]["short_value_sum"] += pos_value
            if win_rate >= 90:
                if pos_value > 0:
                    position_distribution["ge_90"]["long"] += 1
                    position_distribution["ge_90"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["ge_90"]["short"] += 1
                    position_distribution["ge_90"]["short_value_sum"] += pos_value
            if win_rate == 100:
                if pos_value > 0:
                    position_distribution["eq_100"]["long"] += 1
                    position_distribution["eq_100"]["long_value_sum"] += pos_value
                elif pos_value < 0:
                    position_distribution["eq_100"]["short"] += 1
                    position_distribution["eq_100"]["short_value_sum"] += pos_value

        # 计算多空地址数量比值和多空仓位价值总和比值，保留两位小数
        for key in position_distribution:
            long = position_distribution[key]["long"]
            short = position_distribution[key]["short"]
            long_value = position_distribution[key]["long_value_sum"]
            short_value = position_distribution[key]["short_value_sum"]
            position_distribution[key]["ratio"] = (
                round(long / short, 2) if short > 0 else None
            )
            position_distribution[key]["value_ratio"] = (
                round(long_value / abs(short_value), 2)
                if abs(short_value) > 0
                else None
            )
            # 确保价值总和保留三位小数
            position_distribution[key]["long_value_sum"] = round(
                position_distribution[key]["long_value_sum"], 3
            )
            position_distribution[key]["short_value_sum"] = round(
                position_distribution[key]["short_value_sum"], 3
            )

        logger.info(f"多空分布: {position_distribution}")

        # 获取 entry_value_summary 数据
        trades_cursor = web3_hyperliquid_hyper_x_completed_trades_collection.find(
            {"entry_value_summary": {"$exists": True, "$ne": None}},
            {"ethAddress": 1, "entry_value_summary": 1},
        )
        entry_value_data = {
            doc["ethAddress"]: doc["entry_value_summary"] async for doc in trades_cursor
        }
        logger.info(f"获取到 {len(entry_value_data)} 个地址的 entry_value_summary 数据")

        # 需要统计的区间key
        value_keys = [
            "win_rate_over_1w",
            "win_rate_over_10w",
            "win_rate_over_100w",
            "win_rate_over_1000w",
        ]
        # 需要统计的胜率阈值
        winrate_thresholds = [50, 60, 70, 80, 90, 100]

        # 初始化结构
        value_position_distribution = {
            key: {
                f"ge_{thresh}": {
                    "long": 0,
                    "short": 0,
                    "long_value_sum": 0.0,
                    "short_value_sum": 0.0,
                    "ratio": None,
                    "value_ratio": None,
                }
                for thresh in winrate_thresholds
            }
            for key in value_keys
        }

        # 统计每个区间、每个胜率阈值的多空分布
        for addr, entry_summary in entry_value_data.items():
            pos_value = addresses_data.get(addr)
            if pos_value is None:
                continue
            for key in value_keys:
                win_rate = entry_summary.get(key, {}).get("win_rate", 0)
                for thresh in winrate_thresholds:
                    if win_rate >= thresh:
                        d = value_position_distribution[key][f"ge_{thresh}"]
                        if pos_value > 0:
                            d["long"] += 1
                            d["long_value_sum"] += pos_value
                        elif pos_value < 0:
                            d["short"] += 1
                            d["short_value_sum"] += pos_value

        # 计算比值
        for key in value_position_distribution:
            for thresh in winrate_thresholds:
                d = value_position_distribution[key][f"ge_{thresh}"]
                long = d["long"]
                short = d["short"]
                long_value = d["long_value_sum"]
                short_value = d["short_value_sum"]
                d["ratio"] = round(long / short, 2) if short > 0 else None
                d["value_ratio"] = (
                    round(long_value / abs(short_value), 2)
                    if abs(short_value) > 0
                    else None
                )
                d["long_value_sum"] = round(long_value, 3)
                d["short_value_sum"] = round(short_value, 3)

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
        return result

    except Exception as e:
        logger.error(f"分析失败: {e}")
        return {}


def visualize_with_seaborn(result: dict, output_dir: str = "./plots_tmp"):
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
