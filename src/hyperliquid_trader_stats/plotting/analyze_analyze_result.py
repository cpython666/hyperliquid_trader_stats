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
    """按时间升序读取历史分析结果快照。"""
    # 异步加载数据
    cursor = web3_hyperliquid_hyper_x_analyze_result_collection.find().sort("timestamp", 1)
    data = [doc async for doc in cursor]
    return data

async def prepare_data(data):
    """将历史分析快照整理为多空人数比和价值比 DataFrame。"""
    # 准备数据
    rows = []
    for entry in data:
        timestamp = entry["timestamp"]
        for winrate, dist in entry["position_distribution"].items():
            rows.append({
                "timestamp": timestamp,
                "winrate": winrate,
                "ratio": dist["ratio"],
                "value_ratio": dist["value_ratio"]
            })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

async def visualize():
    """导出历史分析数据并绘制多空人数比、价值比趋势图。"""
    # 加载和准备数据
    data = await load_data()
    df = await prepare_data(data)
    print(df.head(15))
    df.to_excel("analyze_result.xlsx", index=False)
    await asyncio.sleep(3)
    # 设置绘图样式
    plt.figure(figsize=(12, 6))

    # 绘制人数比 (ratio) 折线图
    plt.subplot(1, 2, 1)
    sns.lineplot(data=df, x="timestamp", y="ratio", hue="winrate", marker="o")
    plt.title("不同胜率多空人数比随时间变化")
    plt.xlabel("时间")
    plt.ylabel("多空人数比 (Long/Short)")
    plt.legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45)

    # 绘制价值比 (value_ratio) 折线图
    plt.subplot(1, 2, 2)
    sns.lineplot(data=df, x="timestamp", y="value_ratio", hue="winrate", marker="o")
    plt.title("不同胜率多空价值比随时间变化")
    plt.xlabel("时间")
    plt.ylabel("多空价值比 (Long/Short)")
    plt.legend(title="胜率区间", bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45)

    # 调整布局并显示
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    asyncio.run(visualize())
