import asyncio
from datetime import datetime
import os
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_analyze_result_collection,
)

sns.set_style("whitegrid")
plt.rcParams["font.family"] = ["sans-serif"]
plt.rcParams["font.sans-serif"] = ["Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

TYPE_ORDER = [
    "total",
    "win_rate_over_1w",
    "win_rate_over_10w",
    "win_rate_over_100w",
    "win_rate_over_1000w",
]


async def load_history_data():
    """按时间升序读取历史分析结果快照。"""
    cursor = web3_hyperliquid_hyper_x_analyze_result_collection.find().sort(
        "timestamp", 1
    )
    return [doc async for doc in cursor]


def prepare_basic_history_data(data):
    """将历史分析快照整理为基础多空人数比和价值比 DataFrame。"""
    rows = []
    for entry in data:
        timestamp = entry["timestamp"]
        for winrate, dist in entry.get("position_distribution", {}).items():
            rows.append(
                {
                    "timestamp": timestamp,
                    "winrate": winrate,
                    "ratio": dist.get("ratio"),
                    "value_ratio": dist.get("value_ratio"),
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def prepare_grouped_history_data(data):
    """将总胜率和入场价值分层的多空统计展开为 DataFrame。"""
    rows = []
    for entry in data:
        timestamp = entry["timestamp"]
        for winrate, dist in entry.get("position_distribution", {}).items():
            rows.append(
                {
                    "timestamp": timestamp,
                    "type": "total",
                    "zone": winrate,
                    "ratio": dist.get("ratio"),
                    "value_ratio": dist.get("value_ratio"),
                }
            )
        for zone, winrate_dict in entry.get("value_position_distribution", {}).items():
            for winrate, dist in winrate_dict.items():
                rows.append(
                    {
                        "timestamp": timestamp,
                        "type": zone,
                        "zone": winrate,
                        "ratio": dist.get("ratio"),
                        "value_ratio": dist.get("value_ratio"),
                    }
                )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _save_figure(fig, output_dir: Optional[str], name: str):
    if not output_dir:
        return
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, name)
    fig.savefig(path)
    print(f"图表已保存到 {path}")


def _maybe_show(show: bool):
    if show:
        plt.show()
    else:
        plt.close("all")


def visualize_basic_history(
    df,
    *,
    export_excel: Optional[str] = "analyze_result.xlsx",
    output_dir: Optional[str] = None,
    show: bool = True,
):
    """绘制基础历史多空人数比、价值比趋势图。"""
    if df.empty:
        print("没有可用于绘图的历史分析结果。")
        return

    print(df.head(15))
    if export_excel:
        df.to_excel(export_excel, index=False)
        print(f"历史分析数据已导出到 {export_excel}")

    fig = plt.figure(figsize=(12, 6))
    plt.subplot(1, 2, 1)
    sns.lineplot(data=df, x="timestamp", y="ratio", hue="winrate", marker="o")
    plt.title("不同胜率多空人数比随时间变化")
    plt.xlabel("时间")
    plt.ylabel("多空人数比 (Long/Short)")
    plt.legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.xticks(rotation=45)

    plt.subplot(1, 2, 2)
    sns.lineplot(data=df, x="timestamp", y="value_ratio", hue="winrate", marker="o")
    plt.title("不同胜率多空价值比随时间变化")
    plt.xlabel("时间")
    plt.ylabel("多空价值比 (Long/Short)")
    plt.legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.xticks(rotation=45)

    plt.tight_layout()
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    _save_figure(fig, output_dir, f"history_basic_{now}.png")
    _maybe_show(show)


def visualize_grouped_history(
    df,
    *,
    mode: str = "group",
    output_dir: Optional[str] = None,
    show: bool = True,
):
    """按指定模式绘制增强历史多空分布趋势图。"""
    if df.empty:
        print("没有可用于绘图的历史分析结果。")
        return

    types = [t for t in TYPE_ORDER if t in df["type"].unique()]
    now = datetime.now().strftime("%Y%m%d_%H%M%S")

    if mode == "group":
        for t in types:
            df_plot = df[df["type"] == t]
            fig, axes = plt.subplots(1, 2, figsize=(14, 4), sharex=True)
            try:
                fig.canvas.manager.set_window_title(f"{t} 多空统计")
            except Exception:
                pass

            sns.lineplot(
                data=df_plot, x="timestamp", y="ratio", hue="zone", marker="o", ax=axes[0]
            )
            axes[0].set_title(f"{t} 多空人数比随时间变化")
            axes[0].set_xlabel("时间")
            axes[0].set_ylabel("多空人数比 (Long/Short)")
            axes[0].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
            axes[0].tick_params(axis="x", rotation=45)

            sns.lineplot(
                data=df_plot,
                x="timestamp",
                y="value_ratio",
                hue="zone",
                marker="o",
                ax=axes[1],
            )
            axes[1].set_title(f"{t} 多空价值比随时间变化")
            axes[1].set_xlabel("时间")
            axes[1].set_ylabel("多空价值比 (Long/Short)")
            axes[1].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
            axes[1].tick_params(axis="x", rotation=45)

            plt.tight_layout()
            _save_figure(fig, output_dir, f"history_{t}_{now}.png")
        _maybe_show(show)
        return

    fig1, axes1 = plt.subplots(2, 3, figsize=(22, 10), sharex=True)
    fig2, axes2 = plt.subplots(2, 3, figsize=(22, 10), sharex=True)
    try:
        fig1.canvas.manager.set_window_title("多空人数比随时间变化（所有type）")
        fig2.canvas.manager.set_window_title("多空价值比随时间变化（所有type）")
    except Exception:
        pass

    for idx, t in enumerate(types):
        df_plot = df[df["type"] == t]
        row, col = divmod(idx, 3)
        sns.lineplot(
            data=df_plot, x="timestamp", y="ratio", hue="zone", marker="o", ax=axes1[row, col]
        )
        axes1[row, col].set_title(f"{t} 多空人数比随时间变化")
        axes1[row, col].set_xlabel("时间")
        axes1[row, col].set_ylabel("多空人数比 (Long/Short)")
        axes1[row, col].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
        axes1[row, col].tick_params(axis="x", rotation=45)

        sns.lineplot(
            data=df_plot,
            x="timestamp",
            y="value_ratio",
            hue="zone",
            marker="o",
            ax=axes2[row, col],
        )
        axes2[row, col].set_title(f"{t} 多空价值比随时间变化")
        axes2[row, col].set_xlabel("时间")
        axes2[row, col].set_ylabel("多空价值比 (Long/Short)")
        axes2[row, col].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc="upper left")
        axes2[row, col].tick_params(axis="x", rotation=45)

    plt.tight_layout()
    _save_figure(fig1, output_dir, f"history_ratio_big_{now}.png")
    _save_figure(fig2, output_dir, f"history_value_ratio_big_{now}.png")
    _maybe_show(show)


async def visualize_history(
    *,
    basic: bool = False,
    mode: str = "group",
    export_excel: Optional[str] = "analyze_result.xlsx",
    output_dir: Optional[str] = None,
    show: bool = True,
):
    data = await load_history_data()
    if basic:
        df = prepare_basic_history_data(data)
        visualize_basic_history(
            df, export_excel=export_excel, output_dir=output_dir, show=show
        )
    else:
        df = prepare_grouped_history_data(data)
        visualize_grouped_history(df, mode=mode, output_dir=output_dir, show=show)


if __name__ == "__main__":
    asyncio.run(visualize_history())
