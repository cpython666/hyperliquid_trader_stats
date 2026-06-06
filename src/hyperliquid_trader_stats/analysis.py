from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class TraderInput:
    address: str
    fills: list[dict[str, Any]]
    open_position_coins: list[str]
    effective_position_value: float | None = None


SUMMARY_SORT_FIELDS = {
    "address",
    "total_trades",
    "winning_trades",
    "win_rate",
    "win_rate_score",
    "win_rate_wilson_lower_bound",
    "win_rate_long",
    "win_rate_short",
    "gross_pnl",
    "fees",
    "net_pnl",
    "avg_duration_minutes",
    "median_duration_minutes",
    "effective_position_value",
}


def decimal2(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def wilson_lower_bound(wins: int, total: int) -> float:
    if total <= 0:
        return 0.0
    z = 1.96
    phat = wins / total
    return (
        phat
        + z * z / (2 * total)
        - z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    ) / (1 + z * z / total)


def _is_zero(value: Any) -> bool:
    try:
        return Decimal(str(value)) == 0
    except Exception:
        return str(value) in {"0", "0.0"}


def _direction(fill: dict[str, Any]) -> str:
    direction = str(fill.get("dir", ""))
    if "Long" in direction:
        return "Long"
    if "Short" in direction:
        return "Short"
    return direction or "Unknown"


def parse_time_ms(value: str | int | None, *, end_of_day: bool = False) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value * 1000 if value < 10_000_000_000 else value

    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        number = int(raw)
        return number * 1000 if number < 10_000_000_000 else number

    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid date/time value: {value!r}") from exc

    if "T" not in normalized and len(normalized) == 10 and end_of_day:
        parsed = datetime.combine(parsed.date(), time.max)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def filter_fills_by_time(
    fills: list[dict[str, Any]],
    *,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict[str, Any]]:
    filtered = []
    for fill in fills:
        fill_time = int(fill.get("time", 0) or 0)
        if start_time_ms is not None and fill_time < start_time_ms:
            continue
        if end_time_ms is not None and fill_time > end_time_ms:
            continue
        filtered.append(fill)
    return sorted(filtered, key=lambda item: item.get("time", 0))


def sort_results(
    results: list[dict[str, Any]],
    *,
    sort_by: str = "win_rate_wilson_lower_bound",
    descending: bool = True,
) -> list[dict[str, Any]]:
    if sort_by not in SUMMARY_SORT_FIELDS:
        raise ValueError(f"Unsupported sort field: {sort_by}")

    def sort_value(result: dict[str, Any]) -> tuple[Any, float, int, str]:
        summary = result.get("summary", {})
        primary = summary.get(sort_by)
        if sort_by == "address":
            primary = str(primary or "")
        else:
            primary = float(primary or 0)
        return (
            primary,
            float(summary.get("net_pnl") or 0),
            int(summary.get("total_trades") or 0),
            str(summary.get("address") or ""),
        )

    return sorted(results, key=sort_value, reverse=descending)


def merge_fills_to_completed_trades(
    fills: list[dict[str, Any]],
    *,
    open_position_coins: list[str] | None = None,
) -> list[dict[str, Any]]:
    open_position_coins = open_position_coins or []
    sorted_fills = sorted(fills, key=lambda item: item.get("time", 0))
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    counters: dict[str, int] = defaultdict(int)

    for fill in sorted_fills:
        coin = str(fill.get("coin", "UNKNOWN"))
        if _is_zero(fill.get("startPosition")):
            counters[coin] += 1
        groups[(coin, counters[coin])].append(fill)

    trades: list[dict[str, Any]] = []
    for (coin, coin_index), group in groups.items():
        if not group:
            continue

        entry_fills = [fill for fill in group if "Open" in str(fill.get("dir", ""))]
        exit_fills = [fill for fill in group if "Close" in str(fill.get("dir", ""))]
        if not entry_fills or not exit_fills:
            continue

        entry_total_size = sum(Decimal(str(fill.get("sz", "0"))) for fill in entry_fills)
        exit_total_size = sum(Decimal(str(fill.get("sz", "0"))) for fill in exit_fills)
        if entry_total_size == 0 or exit_total_size == 0:
            continue

        entry_avg_price = sum(
            Decimal(str(fill.get("px", "0"))) * Decimal(str(fill.get("sz", "0"))) for fill in entry_fills
        ) / entry_total_size
        exit_avg_price = sum(
            Decimal(str(fill.get("px", "0"))) * Decimal(str(fill.get("sz", "0"))) for fill in exit_fills
        ) / exit_total_size

        total_size = (sum(Decimal(str(fill.get("sz", "0"))) for fill in group) / 2).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_fee = sum(Decimal(str(fill.get("fee", "0"))) for fill in group).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        closed_pnl = sum(Decimal(str(fill.get("closedPnl", "0"))) for fill in group).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net_pnl = (closed_pnl - total_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        start_time_ms = int(group[0].get("time", 0))
        end_time_ms = int(group[-1].get("time", start_time_ms))
        duration_ms = max(0, end_time_ms - start_time_ms)
        invested_capital = entry_avg_price * total_size
        profit_percentage = (
            float((net_pnl / invested_capital * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if invested_capital != 0
            else 0.0
        )

        trades.append(
            {
                "coin": coin,
                "coin_index": coin_index,
                "direction": _direction(group[0]),
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
                "start_time": datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc).isoformat(),
                "end_time": datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc).isoformat(),
                "duration_minutes": round(duration_ms / 60000, 2),
                "total_size": float(total_size),
                "entry_avg_price": decimal2(entry_avg_price),
                "exit_avg_price": decimal2(exit_avg_price),
                "first_entry_price": decimal2(Decimal(str(entry_fills[0].get("px", "0")))),
                "first_exit_price": decimal2(Decimal(str(exit_fills[0].get("px", "0")))),
                "closed_pnl": float(closed_pnl),
                "fees": float(total_fee),
                "net_pnl": float(net_pnl),
                "fills_count": len(group),
                "profit_percentage": profit_percentage,
                "entry_value": decimal2(invested_capital),
            }
        )

    if open_position_coins:
        latest_open_keys = {
            coin: max((trade["coin_index"] for trade in trades if trade["coin"] == coin), default=None)
            for coin in open_position_coins
        }
        trades = [
            trade
            for trade in trades
            if latest_open_keys.get(trade["coin"]) is None or trade["coin_index"] != latest_open_keys[trade["coin"]]
        ]

    return sorted(trades, key=lambda item: item["end_time_ms"])


def analyze_trader(trader: TraderInput) -> dict[str, Any]:
    trades = merge_fills_to_completed_trades(trader.fills, open_position_coins=trader.open_position_coins)
    total_trades = len(trades)
    winning_trades = sum(1 for trade in trades if trade["net_pnl"] > 0)
    win_rate = round(winning_trades / total_trades * 100, 2) if total_trades else 0.0

    long_trades = [trade for trade in trades if trade["direction"] == "Long"]
    short_trades = [trade for trade in trades if trade["direction"] == "Short"]
    durations = [trade["duration_minutes"] for trade in trades]

    stats_per_asset: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "trades": 0, "wins": 0}
    )
    for trade in trades:
        asset = stats_per_asset[trade["coin"]]
        asset["total_pnl"] += trade["closed_pnl"]
        asset["fees"] += trade["fees"]
        asset["net_pnl"] += trade["net_pnl"]
        asset["trades"] += 1
        asset["wins"] += int(trade["net_pnl"] > 0)

    per_asset = {}
    for coin, stats in stats_per_asset.items():
        per_asset[coin] = {
            "trades": stats["trades"],
            "wins": stats["wins"],
            "win_rate": round(stats["wins"] / stats["trades"] * 100, 2) if stats["trades"] else 0.0,
            "total_pnl": round(stats["total_pnl"], 2),
            "fees": round(stats["fees"], 2),
            "net_pnl": round(stats["net_pnl"], 2),
        }

    def side_win_rate(side_trades: list[dict[str, Any]]) -> float:
        return round(sum(1 for trade in side_trades if trade["net_pnl"] > 0) / len(side_trades) * 100, 2) if side_trades else 0.0

    summary = {
        "address": trader.address,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "win_rate_score": round(win_rate * math.log(total_trades + 1), 2) if total_trades else 0.0,
        "win_rate_wilson_lower_bound": round(wilson_lower_bound(winning_trades, total_trades) * 100, 2),
        "win_rate_long": side_win_rate(long_trades),
        "win_rate_short": side_win_rate(short_trades),
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "gross_pnl": round(sum(trade["closed_pnl"] for trade in trades), 2),
        "fees": round(sum(trade["fees"] for trade in trades), 2),
        "net_pnl": round(sum(trade["net_pnl"] for trade in trades), 2),
        "avg_duration_minutes": round(statistics.mean(durations), 2) if durations else 0.0,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else 0.0,
        "effective_position_value": trader.effective_position_value,
        "open_position_coins": ",".join(trader.open_position_coins),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"summary": summary, "trades": trades, "per_asset": per_asset}


def analyze_population(results: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [result["summary"] for result in results]
    thresholds = [50, 60, 70, 80, 90, 100]
    winrate_distribution = {}
    for threshold in thresholds[:-1]:
        winrate_distribution[f"ge_{threshold}"] = sum(1 for item in summaries if item["win_rate"] >= threshold)
    winrate_distribution["eq_100"] = sum(1 for item in summaries if item["win_rate"] == 100)

    position_distribution: dict[str, dict[str, Any]] = {}
    for threshold in thresholds:
        key = f"ge_{threshold}" if threshold < 100 else "eq_100"
        if threshold < 100:
            selected = [item for item in summaries if item["win_rate"] >= threshold]
        else:
            selected = [item for item in summaries if item["win_rate"] == 100]
        longs = [item for item in selected if (item.get("effective_position_value") or 0) > 0]
        shorts = [item for item in selected if (item.get("effective_position_value") or 0) < 0]
        long_value = round(sum(item.get("effective_position_value") or 0 for item in longs), 3)
        short_value = round(sum(item.get("effective_position_value") or 0 for item in shorts), 3)
        position_distribution[key] = {
            "long": len(longs),
            "short": len(shorts),
            "long_value_sum": long_value,
            "short_value_sum": short_value,
            "ratio": round(len(longs) / len(shorts), 2) if shorts else None,
            "value_ratio": round(long_value / abs(short_value), 2) if short_value else None,
        }

    return {
        "total_addresses": len(summaries),
        "analyzed_addresses": sum(1 for item in summaries if item["total_trades"] > 0),
        "winrate_distribution": winrate_distribution,
        "position_distribution": position_distribution,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
