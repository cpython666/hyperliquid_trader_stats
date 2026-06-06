from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

EXPLORER_URL = "https://rpc.hyperliquid.xyz/explorer"
EXPLORER_WS_URL = "wss://rpc.hyperliquid.xyz/ws"
LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
HEADERS = {"Content-Type": "application/json"}


@dataclass(frozen=True)
class BlockScanResult:
    height: int
    addresses: list[str]
    tx_count: int
    invalid_user_count: int


def normalize_address(address: str) -> str:
    return address.lower().strip()


def is_eth_address(value: Any) -> bool:
    return isinstance(value, str) and ETH_ADDRESS_RE.match(value.strip()) is not None


def extract_user_addresses(block_data: dict[str, Any]) -> tuple[list[str], int, int]:
    txs = block_data.get("blockDetails", {}).get("txs", [])
    addresses: list[str] = []
    invalid_count = 0
    for tx in txs:
        user = tx.get("user") if isinstance(tx, dict) else None
        if is_eth_address(user):
            addresses.append(normalize_address(user))
        elif user:
            invalid_count += 1
    return addresses, len(txs), invalid_count


class HyperliquidDiscoveryClient:
    def __init__(
        self,
        *,
        explorer_url: str = EXPLORER_URL,
        explorer_ws_url: str = EXPLORER_WS_URL,
        leaderboard_url: str = LEADERBOARD_URL,
        timeout: int = 15,
        retries: int = 5,
        retry_sleep: float = 2.0,
        rate_limit_sleep: float = 61.0,
    ) -> None:
        self.explorer_url = explorer_url
        self.explorer_ws_url = explorer_ws_url
        self.leaderboard_url = leaderboard_url
        self.timeout = timeout
        self.retries = retries
        self.retry_sleep = retry_sleep
        self.rate_limit_sleep = rate_limit_sleep

    async def fetch_block(self, session: aiohttp.ClientSession, height: int) -> dict[str, Any]:
        payload = {"type": "blockDetails", "height": height}
        for attempt in range(1, self.retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.post(self.explorer_url, headers=HEADERS, json=payload, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict):
                            return data
                        raise RuntimeError(f"unexpected block response type: {type(data)!r}")
                    if response.status == 429:
                        logger.warning("[%s] rate limited, sleeping %.0fs", height, self.rate_limit_sleep)
                        await asyncio.sleep(self.rate_limit_sleep)
                        continue
                    body = await response.text()
                    logger.warning("[%s] failed status=%s attempt=%s body=%s", height, response.status, attempt, body[:200])
            except Exception as exc:
                logger.warning("[%s] request error attempt=%s error=%s", height, attempt, exc)
            await asyncio.sleep(self.retry_sleep)
        raise RuntimeError(f"failed to fetch block {height}")

    async def scan_block(self, session: aiohttp.ClientSession, height: int) -> BlockScanResult:
        data = await self.fetch_block(session, height)
        addresses, tx_count, invalid_count = extract_user_addresses(data)
        return BlockScanResult(
            height=height,
            addresses=addresses,
            tx_count=tx_count,
            invalid_user_count=invalid_count,
        )

    async def get_latest_block_height(self) -> int:
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(self.explorer_ws_url) as ws:
                await ws.send_json({"method": "subscribe", "subscription": {"type": "explorerBlock"}})
                while True:
                    message = await asyncio.wait_for(ws.receive(), timeout=self.timeout)
                    if message.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(message.data)
                        height = self._extract_height_from_ws_message(data)
                        if height is not None:
                            await ws.close()
                            return height
                    if message.type in {aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED}:
                        break
        raise RuntimeError("failed to get latest Hyperliquid explorer block height")

    @staticmethod
    def _extract_height_from_ws_message(data: Any) -> int | None:
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and first.get("height") is not None:
                return int(first["height"])
        if isinstance(data, dict):
            if data.get("height") is not None:
                return int(data["height"])
            payload = data.get("data")
            if isinstance(payload, list) and payload:
                first = payload[0]
                if isinstance(first, dict) and first.get("height") is not None:
                    return int(first["height"])
            if isinstance(payload, dict) and payload.get("height") is not None:
                return int(payload["height"])
        return None

    async def fetch_leaderboard_addresses(self, session: aiohttp.ClientSession) -> list[str]:
        for attempt in range(1, self.retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.get(self.leaderboard_url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        rows = data.get("leaderboardRows", []) if isinstance(data, dict) else []
                        return [
                            normalize_address(row["ethAddress"])
                            for row in rows
                            if isinstance(row, dict) and is_eth_address(row.get("ethAddress"))
                        ]
                    logger.warning("leaderboard failed status=%s attempt=%s", response.status, attempt)
            except Exception as exc:
                logger.warning("leaderboard request error attempt=%s error=%s", attempt, exc)
            await asyncio.sleep(self.retry_sleep)
        raise RuntimeError("failed to fetch Hyperliquid leaderboard")


async def scan_blocks(
    client: HyperliquidDiscoveryClient,
    *,
    start_height: int,
    block_count: int,
    concurrency: int,
) -> list[BlockScanResult]:
    heights = list(range(start_height, start_height - block_count, -1))
    queue: asyncio.Queue[int | None] = asyncio.Queue()
    results: list[BlockScanResult] = []

    for height in heights:
        queue.put_nowait(height)
    for _ in range(concurrency):
        queue.put_nowait(None)

    async with aiohttp.ClientSession() as session:
        async def worker() -> None:
            while True:
                height = await queue.get()
                try:
                    if height is None:
                        return
                    result = await client.scan_block(session, height)
                    results.append(result)
                    logger.info(
                        "[%s] addresses=%s txs=%s invalid_users=%s",
                        height,
                        len(result.addresses),
                        result.tx_count,
                        result.invalid_user_count,
                    )
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await queue.join()
        await asyncio.gather(*workers)

    return sorted(results, key=lambda item: item.height, reverse=True)
