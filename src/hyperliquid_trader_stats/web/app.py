from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hyperliquid_trader_stats.web.queries import (
    get_dashboard_summary,
    get_trader_detail,
    list_trader_trades,
    list_traders,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Hyperliquid Trader Stats",
    description="Browse computed Hyperliquid trader win-rate and position data.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/leaderboard", include_in_schema=False)
async def leaderboard():
    return FileResponse(STATIC_DIR / "leaderboard.html")


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/dashboard")
async def dashboard():
    return await get_dashboard_summary()


@app.get("/api/traders")
async def traders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    min_win_rate: Optional[float] = Query(None, ge=0, le=100),
    max_win_rate: Optional[float] = Query(None, ge=0, le=100),
    min_total_trades: Optional[int] = Query(None, ge=0),
    max_total_trades: Optional[int] = Query(None, ge=0),
    min_net_pnl: Optional[float] = None,
    max_net_pnl: Optional[float] = None,
    min_position_value: Optional[float] = None,
    max_position_value: Optional[float] = None,
    position_direction: str = Query("any", pattern="^(any|long|short|flat|unknown)$"),
    entry_value_tier: str = Query("all", pattern="^(all|1w|10w|100w|1000w)$"),
    min_entry_win_rate: Optional[float] = Query(None, ge=0, le=100),
    updated_after: Optional[datetime] = None,
    updated_before: Optional[datetime] = None,
    sort_by: str = Query(
        "win_rate_score",
        pattern="^(win_rate|win_rate_score|wilson|total_trades|net_pnl|pnl|fees|avg_duration|updated_at|processed_through|position_value|account_value)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    return await list_traders(
        page=page,
        page_size=page_size,
        search=search,
        min_win_rate=min_win_rate,
        max_win_rate=max_win_rate,
        min_total_trades=min_total_trades,
        max_total_trades=max_total_trades,
        min_net_pnl=min_net_pnl,
        max_net_pnl=max_net_pnl,
        min_position_value=min_position_value,
        max_position_value=max_position_value,
        position_direction=position_direction,
        entry_value_tier=entry_value_tier,
        min_entry_win_rate=min_entry_win_rate,
        updated_after=updated_after,
        updated_before=updated_before,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.get("/api/traders/{address}")
async def trader_detail(address: str):
    result = await get_trader_detail(address)
    if result is None:
        raise HTTPException(status_code=404, detail="trader not found")
    return result


@app.get("/api/traders/{address}/trades")
async def trader_trades(
    address: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    result = await list_trader_trades(
        address,
        page=page,
        page_size=page_size,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="trader not found")
    return result
