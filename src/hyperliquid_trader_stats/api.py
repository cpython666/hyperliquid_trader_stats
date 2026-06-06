from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
UI_INFO_URL = "https://api-ui.hyperliquid.xyz/info"
HEADERS = {"Content-Type": "application/json"}


@dataclass(frozen=True)
class UserState:
    raw: dict[str, Any]
    open_position_coins: list[str]
    effective_position_value: float


class HyperliquidClient:
    def __init__(
        self,
        *,
        info_url: str = INFO_URL,
        fills_url: str = UI_INFO_URL,
        timeout: int = 20,
        retries: int = 3,
        retry_sleep: float = 2.0,
        rate_limit_sleep: float = 61.0,
    ) -> None:
        self.info_url = info_url
        self.fills_url = fills_url
        self.timeout = timeout
        self.retries = retries
        self.retry_sleep = retry_sleep
        self.rate_limit_sleep = rate_limit_sleep

    async def _post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, Any],
    ) -> Any:
        for attempt in range(1, self.retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.post(url, headers=HEADERS, json=payload, timeout=timeout) as response:
                    if response.status == 200:
                        return await response.json()
                    if response.status == 429:
                        logger.warning("Hyperliquid 接口触发限流，等待 %.0f 秒后重试", self.rate_limit_sleep)
                        await asyncio.sleep(self.rate_limit_sleep)
                        continue
                    text = await response.text()
                    logger.warning("请求失败：状态=%s 第 %s 次尝试 响应=%s", response.status, attempt, text[:300])
            except Exception as exc:
                logger.warning("请求异常：第 %s 次尝试 请求类型=%s 错误=%s", attempt, payload.get("type"), exc)
            await asyncio.sleep(self.retry_sleep)
        raise RuntimeError(f"Hyperliquid 请求重试 {self.retries} 次后仍失败：{payload.get('type')}")

    async def fetch_user_fills(
        self,
        session: aiohttp.ClientSession,
        address: str,
        *,
        start_time: int = 0,
        end_time: int | None = None,
        aggregate_by_time: bool = True,
        page_size_stop: int = 2000,
    ) -> list[dict[str, Any]]:
        all_fills: list[dict[str, Any]] = []
        seen_tids: set[Any] = set()
        current_start_time = start_time

        # userFillsByTime 需要按 time 续页；用 tid 去重可避免翻页边界重复。
        while True:
            payload = {
                "type": "userFillsByTime",
                "user": address,
                "startTime": current_start_time,
                "aggregateByTime": aggregate_by_time,
            }
            if end_time is not None:
                payload["endTime"] = end_time
            data = await self._post(session, self.fills_url, payload)
            fills = data.get("fills", []) if isinstance(data, dict) else data
            if not isinstance(fills, list):
                raise RuntimeError(f"地址 {address} 的 fills 响应类型异常：{type(fills)!r}")

            new_fills = []
            for fill in fills:
                fill_time = int(fill.get("time", 0) or 0)
                if end_time is not None and fill_time > end_time:
                    continue
                tid = fill.get("tid")
                if tid in seen_tids:
                    continue
                seen_tids.add(tid)
                new_fills.append(fill)
            all_fills.extend(new_fills)

            if len(fills) < page_size_stop:
                return sorted(all_fills, key=lambda item: item.get("time", 0))

            next_start_time = fills[-1].get("time")
            if next_start_time is None or next_start_time == current_start_time:
                return sorted(all_fills, key=lambda item: item.get("time", 0))
            if end_time is not None and int(next_start_time) >= end_time:
                return sorted(all_fills, key=lambda item: item.get("time", 0))
            current_start_time = int(next_start_time)

    async def fetch_user_state(self, session: aiohttp.ClientSession, address: str) -> UserState:
        payload = {"type": "clearinghouseState", "user": address}
        state = await self._post(session, self.info_url, payload)
        asset_positions = state.get("assetPositions", []) if isinstance(state, dict) else []
        open_coins: list[str] = []
        effective_value = Decimal("0")

        for item in asset_positions:
            position = item.get("position", {}) if isinstance(item, dict) else {}
            coin = position.get("coin")
            if coin:
                open_coins.append(str(coin))
            position_value = position.get("positionValue")
            szi = position.get("szi")
            if position_value is None or szi is None:
                continue
            try:
                value = Decimal(str(position_value))
                size = Decimal(str(szi))
            except Exception:
                continue
            effective_value += value if size >= 0 else -value

        effective_value = effective_value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return UserState(raw=state, open_position_coins=open_coins, effective_position_value=float(effective_value))
