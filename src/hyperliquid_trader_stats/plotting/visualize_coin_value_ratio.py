from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any, Optional

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from bson import ObjectId
from bson.errors import InvalidId

from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_analyze_result_collection,
)

sns.set_style("whitegrid")
plt.rcParams["font.family"] = ["sans-serif"]
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

WINRATE_KEYS = ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]
GROUPED_WINRATE_KEYS = ["eq_100", "ge_90", "ge_80", "ge_70", "ge_60", "ge_50"]
WINRATE_LABELS = {
    "eq_100": "=100",
    "ge_90": "≥90",
    "ge_80": "≥80",
    "ge_70": "≥70",
    "ge_60": "≥60",
    "ge_50": "≥50",
}
async def load_analysis_snapshot(analysis_id: Optional[str] = None) -> Optional[dict]:
    """读取指定 _id 的分析快照；未指定时读取 timestamp 最新的一条。"""
    if analysis_id:
        try:
            object_id = ObjectId(analysis_id)
        except InvalidId as error:
            raise ValueError(f"无效的 MongoDB ObjectId: {analysis_id}") from error
        return await web3_hyperliquid_hyper_x_analyze_result_collection.find_one(
            {"_id": object_id}
        )

    return await web3_hyperliquid_hyper_x_analyze_result_collection.find_one(
        {},
        sort=[("timestamp", -1)],
    )


def _coin_distribution(snapshot: dict[str, Any]) -> dict[str, Any]:
    coin_distribution = snapshot.get("coin_position_distribution", {})
    return coin_distribution if isinstance(coin_distribution, dict) else {}


def _ratio_row(coin: str, winrate_key: str, item: dict[str, Any]) -> Optional[dict[str, Any]]:
    long_value = float(item.get("long_value_sum") or 0)
    short_value = abs(float(item.get("short_value_sum") or 0))
    if long_value <= 0 and short_value <= 0:
        return None

    if short_value > 0:
        value_ratio = round(long_value / short_value, 4)
        display_ratio: str | float = value_ratio
    elif long_value > 0:
        value_ratio = math.inf
        display_ratio = "∞"
    else:
        value_ratio = 0.0
        display_ratio = 0.0

    return {
        "coin": coin,
        "winrate_key": winrate_key,
        "winrate_label": WINRATE_LABELS[winrate_key],
        "value_ratio": value_ratio,
        "display_ratio": display_ratio,
        "long_value_sum": long_value,
        "short_value_abs": short_value,
        "long": item.get("long", 0),
        "short": item.get("short", 0),
    }


def prepare_single_winrate_rows(
    snapshot: dict[str, Any],
    *,
    winrate_key: str,
) -> list[dict[str, Any]]:
    """提取指定胜率门槛的币种多空价值比；指定门槛时全量展示。"""
    rows = []
    for coin, distribution in _coin_distribution(snapshot).items():
        if not isinstance(distribution, dict):
            continue
        item = distribution.get(winrate_key, {})
        if not isinstance(item, dict):
            continue
        row = _ratio_row(coin, winrate_key, item)
        if row is not None:
            rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            math.isinf(row["value_ratio"]),
            row["value_ratio"],
            row["long_value_sum"],
        ),
        reverse=True,
    )


def prepare_grouped_coin_rows(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """按 ge_50 仓位价值总和排序，并保留各门槛价值比用于展示。"""
    coin_distribution = _coin_distribution(snapshot)
    rows = []

    for coin, distribution in coin_distribution.items():
        if not isinstance(distribution, dict):
            continue

        ratio_rows = []
        ge50_position_value_sum = 0.0
        for winrate_key in GROUPED_WINRATE_KEYS:
            item = distribution.get(winrate_key, {})
            if not isinstance(item, dict):
                continue
            row = _ratio_row(coin, winrate_key, item)
            if row is None:
                continue

            row["position_value_sum"] = row["long_value_sum"] + row["short_value_abs"]
            ratio_rows.append(row)
            if winrate_key == "ge_50":
                ge50_position_value_sum = row["position_value_sum"]

        if ratio_rows and ge50_position_value_sum > 0:
            rows.append(
                {
                    "coin": coin,
                    "ge50_position_value_sum": round(ge50_position_value_sum, 3),
                    "ratios": ratio_rows,
                }
            )

    return sorted(
        rows,
        key=lambda row: row["ge50_position_value_sum"],
        reverse=True,
    )


def _snapshot_label(snapshot: dict[str, Any]) -> str:
    timestamp = snapshot.get("timestamp")
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return str(timestamp or "unknown")


def _finite_ratio_values(rows: list[dict[str, Any]], field: str = "value_ratio") -> list[float]:
    return [
        float(row[field])
        for row in rows
        if isinstance(row[field], (int, float))
        and not math.isinf(row[field])
    ]


def _plot_axis_cap(rows: list[dict[str, Any]], field: str = "value_ratio") -> float:
    """给绘图用的 x 轴上限；不改变原始标签，只避免极端值压扁图。"""
    finite_values = sorted(value for value in _finite_ratio_values(rows, field) if value > 0)
    if not finite_values:
        return 1.0
    quantile_index = min(
        len(finite_values) - 1,
        max(0, int((len(finite_values) - 1) * 0.95)),
    )
    quantile_cap = finite_values[quantile_index] * 1.2
    hard_cap = max(10.0, quantile_cap)
    return min(max(finite_values), hard_cap)


def _safe_ratio_for_plot(rows: list[dict[str, Any]], field: str = "value_ratio") -> list[float]:
    cap = _plot_axis_cap(rows, field)
    return [
        cap * 0.012
        if math.isinf(row[field])
        else min(float(row[field]), cap)
        for row in rows
    ]


def _is_clipped(row: dict[str, Any], cap: float, field: str = "value_ratio") -> bool:
    value = row[field]
    return isinstance(value, (int, float)) and not math.isinf(value) and value > cap


def _label_x_position(plot_value: float, cap: float) -> float:
    if plot_value <= 0:
        return cap * 1.01
    return plot_value + cap * 0.01


def _format_plot_label(row: dict[str, Any], cap: float) -> str:
    label = _format_ratio_label(row["display_ratio"])
    if _is_clipped(row, cap):
        label = f"// {label}"
    return label


def _format_ratio_label(value: Any) -> str:
    """格式化原始多空价值比；∞ 保持为 ∞，有限值不使用绘图替代值。"""
    if value == "∞":
        return "∞"
    if isinstance(value, (int, float)):
        if math.isinf(value):
            return "∞"
        if abs(value) >= 100:
            return f"{value:.2f}"
        return f"{value:.4g}"
    return str(value)


def plot_single_winrate_ratios(
    rows: list[dict[str, Any]],
    *,
    snapshot: dict[str, Any],
    winrate_key: str,
    output_dir: Optional[str] = None,
    show: bool = True,
) -> Optional[str]:
    """绘制币种多空价值比横向柱状图，返回保存路径。"""
    if not rows:
        print("没有可用于绘图的币种多空价值比数据。")
        return None

    df = pd.DataFrame(rows)
    df["plot_ratio"] = _safe_ratio_for_plot(rows)
    cap = _plot_axis_cap(rows)

    height = max(6, min(28, 0.42 * len(df) + 2))
    fig, ax = plt.subplots(figsize=(12, height))
    sns.barplot(data=df, y="coin", x="plot_ratio", ax=ax, color="#4c78a8")

    title = f"币种多空价值比排行（{winrate_key}，快照 {_snapshot_label(snapshot)}）"
    ax.set_title(title)
    ax.set_xlabel("多空价值比 = 多头仓位价值 / 空头仓位价值绝对值")
    ax.set_ylabel("币种")

    for index, row in df.reset_index(drop=True).iterrows():
        label = (
            f"{_format_plot_label(row, cap)}  "
            f"L ${row['long_value_sum']:,.0f} / S ${row['short_value_abs']:,.0f}"
        )
        ax.text(
            _label_x_position(row["plot_ratio"], cap),
            index,
            f" {label}",
            va="center",
            fontsize=9,
        )

    ax.set_xlim(0, cap * 1.18)

    plt.tight_layout()

    saved_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = str(snapshot.get("_id", "latest"))
        saved_path = os.path.join(
            output_dir,
            f"coin_value_ratio_{winrate_key}_{snapshot_id}_{now}.png",
        )
        fig.savefig(saved_path, dpi=160)
        print(f"图表已保存到 {saved_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved_path


def _flatten_grouped_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat_rows = []
    for row in rows:
        for ratio in row["ratios"]:
            flat_rows.append(
                {
                    **ratio,
                    "coin_label": (
                        f"{row['coin']}  (${row['ge50_position_value_sum']:,.0f})"
                    ),
                    "ge50_position_value_sum": row["ge50_position_value_sum"],
                }
            )
    return flat_rows


def plot_grouped_coin_ratios(
    rows: list[dict[str, Any]],
    *,
    snapshot: dict[str, Any],
    output_dir: Optional[str] = None,
    show: bool = True,
) -> Optional[str]:
    """绘制按仓位价值排序后的币种分组柱状图。"""
    if not rows:
        print("没有可用于绘图的币种多空价值比数据。")
        return None

    flat_rows = _flatten_grouped_rows(rows)
    plot_ratios = _safe_ratio_for_plot(flat_rows)
    cap = _plot_axis_cap(flat_rows)
    for row, plot_ratio in zip(flat_rows, plot_ratios):
        row["plot_ratio"] = plot_ratio
    row_by_coin_and_key = {
        (row["coin"], row["winrate_key"]): row
        for row in flat_rows
    }

    height = max(7, min(32, 0.55 * len(rows) + 2))
    fig, ax = plt.subplots(figsize=(14, height))
    y_positions = list(range(len(rows)))
    group_height = 0.82
    bar_height = group_height / len(GROUPED_WINRATE_KEYS)

    for key_index, winrate_key in enumerate(GROUPED_WINRATE_KEYS):
        offset = (key_index - (len(GROUPED_WINRATE_KEYS) - 1) / 2) * bar_height
        xs = []
        ys = []
        labels = []
        for coin_index, coin_row in enumerate(rows):
            ratio_row = row_by_coin_and_key.get((coin_row["coin"], winrate_key))
            xs.append(ratio_row["plot_ratio"] if ratio_row else 0)
            ys.append(y_positions[coin_index] + offset)
            labels.append(ratio_row)

        bars = ax.barh(
            ys,
            xs,
            height=bar_height * 0.88,
            label=WINRATE_LABELS[winrate_key],
        )
        for bar, ratio_row in zip(bars, labels):
            if ratio_row is None:
                continue
            label = _format_plot_label(ratio_row, cap)
            if math.isinf(ratio_row["value_ratio"]):
                marker_x = max(bar.get_width(), cap * 0.012)
                y = bar.get_y() + bar.get_height() / 2
                ax.vlines(
                    marker_x,
                    y - bar.get_height() * 0.48,
                    y + bar.get_height() * 0.48,
                    colors=bar.get_facecolor(),
                    linestyles="dashed",
                    linewidth=1,
                )
            ax.text(
                _label_x_position(bar.get_width(), cap),
                bar.get_y() + bar.get_height() / 2,
                label,
                va="center",
                fontsize=7,
            )

    title = f"币种多空价值比排行（按 ≥50 胜率仓位价值排序，快照 {_snapshot_label(snapshot)}）"
    ax.set_title(title)
    ax.set_xlabel("多空价值比 = 多头仓位价值 / 空头仓位价值绝对值")
    ax.set_ylabel("币种（括号内为 ≥50 胜率仓位价值）")
    ax.set_yticks(y_positions)
    ax.set_yticklabels(
        [f"{row['coin']}  (${row['ge50_position_value_sum']:,.0f})" for row in rows]
    )
    ax.invert_yaxis()
    ax.set_xlim(0, cap * 1.18)
    ax.legend(title="胜率门槛", bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.tight_layout()

    saved_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = str(snapshot.get("_id", "latest"))
        saved_path = os.path.join(
            output_dir,
            f"coin_value_ratio_grouped_{snapshot_id}_{now}.png",
        )
        fig.savefig(saved_path, dpi=160)
        print(f"图表已保存到 {saved_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved_path


async def visualize_coin_value_ratio(
    *,
    analysis_id: Optional[str] = None,
    winrate_key: Optional[str] = None,
    top: int = 30,
    output_dir: Optional[str] = "plots_tmp",
    show: bool = True,
) -> Optional[str]:
    """加载分析快照并可视化币种多空价值比。"""
    if winrate_key is not None and winrate_key not in WINRATE_KEYS:
        raise ValueError(f"winrate_key 必须是 {', '.join(WINRATE_KEYS)} 之一")
    if top < 1:
        raise ValueError("top 必须大于等于 1")

    snapshot = await load_analysis_snapshot(analysis_id)
    if snapshot is None:
        identifier = analysis_id or "最新记录"
        print(f"未找到分析快照：{identifier}")
        return None

    if winrate_key is not None:
        rows = prepare_single_winrate_rows(snapshot, winrate_key=winrate_key)
        if rows:
            print(f"{winrate_key} 多空价值比最高的币种：")
            for row in rows[:10]:
                print(
                    f"{row['coin']}: {row['display_ratio']} "
                    f"(long=${row['long_value_sum']:,.2f}, "
                    f"short=${row['short_value_abs']:,.2f})"
                )
        return plot_single_winrate_ratios(
            rows,
            snapshot=snapshot,
            winrate_key=winrate_key,
            output_dir=output_dir,
            show=show,
        )

    rows = prepare_grouped_coin_rows(snapshot)[:top]
    if rows:
        print("仓位价值最高的币种：")
        for row in rows[:10]:
            print(
                f"{row['coin']}: ge_50仓位价值=${row['ge50_position_value_sum']:,.2f}"
            )
    return plot_grouped_coin_ratios(
        rows,
        snapshot=snapshot,
        output_dir=output_dir,
        show=show,
    )
