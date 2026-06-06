from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_dashboard(
    results: list[dict[str, Any]],
    population: dict[str, Any],
    output: str | Path,
    *,
    sort_by: str = "win_rate_wilson_lower_bound",
    sort_desc: bool = True,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame([result["summary"] for result in results])
    trades = pd.DataFrame(
        [{"address": result["summary"]["address"], **trade} for result in results for trade in result["trades"]]
    )

    if summary.empty:
        html = "<html><body><h1>Hyperliquid Trader Stats</h1><p>No data.</p></body></html>"
        output_path.write_text(html, encoding="utf-8")
        return output_path

    sort_columns = [column for column in [sort_by, "net_pnl", "total_trades"] if column in summary.columns]
    summary = summary.sort_values(sort_columns, ascending=not sort_desc, na_position="last")
    top = summary.head(50).copy()
    top["short_address"] = top["address"].str.slice(0, 8) + "..." + top["address"].str.slice(-6)

    top_fig = px.bar(
        top,
        x="short_address",
        y="win_rate",
        color="net_pnl",
        hover_data=["address", "total_trades", "winning_trades", "win_rate_wilson_lower_bound", "net_pnl"],
        title="Top traders by win rate",
        labels={"short_address": "address", "win_rate": "win rate (%)", "net_pnl": "net PnL"},
        color_continuous_scale=["#d84a3a", "#f2c14e", "#248a63"],
    )
    top_fig.update_layout(height=520, xaxis_tickangle=-45)

    dist_items = population.get("position_distribution", {})
    labels = ["ge_50", "ge_60", "ge_70", "ge_80", "ge_90", "eq_100"]
    label_names = [">=50", ">=60", ">=70", ">=80", ">=90", "=100"]
    dist_fig = make_subplots(specs=[[{"secondary_y": True}]])
    dist_fig.add_trace(go.Bar(name="long count", x=label_names, y=[dist_items.get(k, {}).get("long", 0) for k in labels]))
    dist_fig.add_trace(go.Bar(name="short count", x=label_names, y=[dist_items.get(k, {}).get("short", 0) for k in labels]))
    dist_fig.add_trace(
        go.Scatter(
            name="long/short value ratio",
            x=label_names,
            y=[dist_items.get(k, {}).get("value_ratio") or 0 for k in labels],
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    dist_fig.update_layout(title="Current long/short distribution by win-rate threshold", height=440)
    dist_fig.update_yaxes(title_text="trader count", secondary_y=False)
    dist_fig.update_yaxes(title_text="value ratio", secondary_y=True)

    pnl_fig = px.scatter(
        summary,
        x="total_trades",
        y="win_rate",
        size=summary["net_pnl"].abs().clip(lower=1),
        color="net_pnl",
        hover_data=["address", "winning_trades", "win_rate_wilson_lower_bound", "win_rate_long", "win_rate_short"],
        title="Win rate vs trade count",
        labels={"total_trades": "completed trades", "win_rate": "win rate (%)"},
        color_continuous_scale=["#d84a3a", "#f2c14e", "#248a63"],
    )
    pnl_fig.update_layout(height=500)

    if not trades.empty:
        daily = trades.copy()
        daily["end_date"] = pd.to_datetime(daily["end_time"]).dt.date
        daily_pnl = daily.groupby("end_date", as_index=False)["net_pnl"].sum()
        daily_fig = px.line(daily_pnl, x="end_date", y="net_pnl", markers=True, title="Closed trade net PnL by day")
    else:
        daily_fig = go.Figure()
        daily_fig.update_layout(title="Closed trade net PnL by day")

    table_cols = [
        "address",
        "total_trades",
        "winning_trades",
        "win_rate",
        "win_rate_wilson_lower_bound",
        "win_rate_long",
        "win_rate_short",
        "net_pnl",
        "fees",
        "avg_duration_minutes",
        "effective_position_value",
    ]
    table_html = summary[table_cols].to_html(index=False, classes="data-table", float_format=lambda value: f"{value:.2f}")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hyperliquid Trader Stats</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18212f;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #226f68;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 28px 40px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    .meta {{ color: var(--muted); display: flex; gap: 18px; flex-wrap: wrap; }}
    main {{ padding: 24px 40px 48px; display: grid; gap: 22px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
    }}
    .data-table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    .data-table th, .data-table td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: right; }}
    .data-table th:first-child, .data-table td:first-child {{ text-align: left; }}
    .data-table th {{ background: #eef2f6; position: sticky; top: 0; }}
    @media (max-width: 760px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Hyperliquid Trader Stats</h1>
    <div class="meta">
      <span>addresses: {population.get("total_addresses", len(summary))}</span>
      <span>analyzed: {population.get("analyzed_addresses", 0)}</span>
      <span>updated: {population.get("timestamp", "")}</span>
    </div>
  </header>
  <main>
    <section>{top_fig.to_html(full_html=False, include_plotlyjs="cdn")}</section>
    <section>{dist_fig.to_html(full_html=False, include_plotlyjs=False)}</section>
    <section>{pnl_fig.to_html(full_html=False, include_plotlyjs=False)}</section>
    <section>{daily_fig.to_html(full_html=False, include_plotlyjs=False)}</section>
    <section>{table_html}</section>
  </main>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path
