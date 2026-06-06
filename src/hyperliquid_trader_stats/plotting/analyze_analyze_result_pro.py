import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import asyncio
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_analyze_result_collection
# 1. 先设置 Seaborn 样式
sns.set_style("whitegrid")

# 2. 再覆盖 Seaborn 可能重置掉的 Matplotlib rcParams
plt.rcParams['font.family'] = ['sans-serif']
plt.rcParams['font.sans-serif'] = ['Heiti TC']
plt.rcParams['axes.unicode_minus'] = False


async def load_data():
    # 异步加载数据
    cursor = web3_hyperliquid_hyper_x_analyze_result_collection.find().sort("timestamp", 1)
    data = [doc async for doc in cursor]
    return data

async def prepare_data(data):
    # 准备数据
    rows = []
    for entry in data:
        timestamp = entry["timestamp"]
        # 处理 position_distribution（总胜率分布）
        for winrate, dist in entry.get("position_distribution", {}).items():
            rows.append({
                "timestamp": timestamp,
                "type": "total",
                "zone": winrate,
                "ratio": dist.get("ratio"),
                "value_ratio": dist.get("value_ratio")
            })
        # 处理 value_position_distribution（各仓位价值区间+胜率分布）
        for zone, winrate_dict in entry.get("value_position_distribution", {}).items():
            for winrate, dist in winrate_dict.items():
                rows.append({
                    "timestamp": timestamp,
                    "type": zone,  # 如 win_rate_over_1w
                    "zone": winrate,  # 如 ge_50
                    "ratio": dist.get("ratio"),
                    "value_ratio": dist.get("value_ratio")
                })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

async def visualize(mode="group"):
    """
    mode: "group" 每个type一组两图，共多张图；"big" 所有type放一张大图（2x2子图），共两张大图
    """
    data = await load_data()
    df = await prepare_data(data)
    await asyncio.sleep(1)

    type_order = ["total", "win_rate_over_1w", "win_rate_over_10w", "win_rate_over_100w", "win_rate_over_1000w"]
    types = [t for t in type_order if t in df["type"].unique()]  # 不限制数量

    if mode == "group":
        figs = []
        # 每个type一组（两图），共多张图
        for t in types:
            df_plot = df[df["type"] == t]
            fig, axes = plt.subplots(1, 2, figsize=(14, 4), sharex=True)
            figs.append(fig)
            # 设置窗口标题
            try:
                fig.canvas.manager.set_window_title(f"{t} 多空统计")
            except Exception:
                pass  # 某些环境下可能不支持

            sns.lineplot(data=df_plot, x="timestamp", y="ratio", hue="zone", marker="o",  ax=axes[0])
            axes[0].set_title(f"{t} 多空人数比随时间变化")
            axes[0].set_xlabel("时间")
            axes[0].set_ylabel("多空人数比 (Long/Short)")
            axes[0].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
            axes[0].tick_params(axis='x', rotation=45)

            sns.lineplot(data=df_plot, x="timestamp", y="value_ratio", hue="zone", marker="o",  ax=axes[1])
            axes[1].set_title(f"{t} 多空价值比随时间变化")
            axes[1].set_xlabel("时间")
            axes[1].set_ylabel("多空价值比 (Long/Short)")
            axes[1].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
            axes[1].tick_params(axis='x', rotation=45)

            plt.tight_layout()
        plt.show()
    elif mode == "big":
        # 所有type放一张大图（2x3子图），共两张大图
        fig1, axes1 = plt.subplots(2, 3, figsize=(22, 10), sharex=True)
        fig2, axes2 = plt.subplots(2, 3, figsize=(22, 10), sharex=True)
        # 设置窗口标题
        try:
            fig1.canvas.manager.set_window_title("多空人数比随时间变化（所有type）")
            fig2.canvas.manager.set_window_title("多空价值比随时间变化（所有type）")
        except Exception:
            pass  # 某些环境下可能不支持

        for idx, t in enumerate(types):
            df_plot = df[df["type"] == t]
            row, col = divmod(idx, 3)
            # 人数比
            sns.lineplot(data=df_plot, x="timestamp", y="ratio", hue="zone", marker="o",  ax=axes1[row, col])
            axes1[row, col].set_title(f"{t} 多空人数比随时间变化")
            axes1[row, col].set_xlabel("时间")
            axes1[row, col].set_ylabel("多空人数比 (Long/Short)")
            axes1[row, col].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
            axes1[row, col].tick_params(axis='x', rotation=45)
            # 价值比
            sns.lineplot(data=df_plot, x="timestamp", y="value_ratio", hue="zone", marker="o",  ax=axes2[row, col])
            axes2[row, col].set_title(f"{t} 多空价值比随时间变化")
            axes2[row, col].set_xlabel("时间")
            axes2[row, col].set_ylabel("多空价值比 (Long/Short)")
            axes2[row, col].legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
            axes2[row, col].tick_params(axis='x', rotation=45)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    # mode="group" 或 mode="big"
    # asyncio.run(visualize(mode="big"))
    asyncio.run(visualize(mode="group"))