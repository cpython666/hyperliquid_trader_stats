import asyncio
import json
import queue
import threading
import time

import aiohttp
import requests
import websocket
from web3 import Web3

from hyperliquid_trader_stats.config import (
    AIOHTTP_PROXY,
    REQUESTS_PROXIES,
    WEBSOCKET_PROXY_KWARGS,
)
from hyperliquid_trader_stats.hyper_x_utils import save_addresses

EXPLORER_URL = "https://rpc.hyperliquid.xyz/explorer"
WEBSOCKET_URL = "wss://rpc.hyperliquid.xyz/ws"
MAX_RETRIES = 5


def _extract_valid_addresses(data):
    txs = data.get("blockDetails", {}).get("txs", [])
    addresses = [tx.get("user") for tx in txs if Web3.is_address(tx.get("user"))]
    invalid_addresses = [
        tx.get("user") for tx in txs if not Web3.is_address(tx.get("user"))
    ]
    return addresses, invalid_addresses


async def _save_block_addresses(height: int, data):
    addresses, invalid_addresses = _extract_valid_addresses(data)
    print(f"[{height}] ✅ 有效地址: {len(addresses)}，❌ 非地址: {len(invalid_addresses)}")
    if addresses:
        await save_addresses(addresses)


async def _fetch_block_with_aiohttp(session, height: int, semaphore: asyncio.Semaphore):
    headers = {"Content-Type": "application/json"}
    payload = {"type": "blockDetails", "height": height}

    retry = 0
    while retry < MAX_RETRIES:
        async with semaphore:
            try:
                async with session.post(
                    EXPLORER_URL,
                    json=payload,
                    headers=headers,
                    timeout=5,
                    proxy=AIOHTTP_PROXY,
                ) as response:
                    if response.status == 200:
                        await _save_block_addresses(height, await response.json())
                        return

                    if response.status == 429:
                        print(f"[{height}] ⚠️ 429 Too Many Requests，等待 61 秒再试...")
                        await asyncio.sleep(61)
                        retry += 1
                        continue

                    print(f"[{height}] ❌ 请求失败，状态码: {response.status}")
                    return
            except Exception as error:
                print(f"[{height}] ❌ 请求异常: {error}")
                await asyncio.sleep(3)
                retry += 1


def _sync_fetch_block(height: int):
    headers = {"Content-Type": "application/json"}
    payload = {"type": "blockDetails", "height": height}

    for _retry in range(MAX_RETRIES):
        try:
            response = requests.post(
                EXPLORER_URL,
                json=payload,
                headers=headers,
                timeout=5,
                proxies=REQUESTS_PROXIES,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                print(f"[{height}] ⚠️ 429 Too Many Requests，等待重试...")
                time.sleep(60)
                continue
            print(f"[{height}] ❌ 请求失败，状态码: {response.status_code}")
            return None
        except Exception as error:
            print(f"[{height}] ❌ 请求异常: {error}")
            time.sleep(3)
    return None


async def _fetch_block_with_requests(height: int, semaphore: asyncio.Semaphore):
    async with semaphore:
        data = await asyncio.to_thread(_sync_fetch_block, height)
    if data is not None:
        await _save_block_addresses(height, data)


async def fetch_and_store_addresses_from_block(
    start_height: int,
    block_count: int = 1000,
    *,
    backend: str = "aiohttp",
    concurrency: int | None = None,
):
    """从起始区块向前批量扫描指定数量的区块地址。"""
    if backend not in {"aiohttp", "requests"}:
        raise ValueError("backend 必须是 aiohttp 或 requests")

    max_concurrency = concurrency if concurrency is not None else (10 if backend == "requests" else 5)
    semaphore = asyncio.Semaphore(max_concurrency)
    heights = range(start_height, start_height - block_count, -1)

    if backend == "requests":
        tasks = [_fetch_block_with_requests(height, semaphore) for height in heights]
        await asyncio.gather(*tasks)
        return

    async with aiohttp.ClientSession() as session:
        tasks = [
            _fetch_block_with_aiohttp(session, height, semaphore) for height in heights
        ]
        await asyncio.gather(*tasks)


def get_block_height():
    """获取最新区块高度并返回。"""
    height_queue = queue.Queue()

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, list) and data:
                height = data[0].get("height")
                if height:
                    height_queue.put(height)
                    ws.close()
        except json.JSONDecodeError as error:
            print(f"JSON decode error: {error}")

    def on_error(ws, error):
        print(f"Error: {error}")
        height_queue.put(None)
        ws.close()

    def on_open(ws):
        print("WebSocket opened")
        ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "subscription": {"type": "explorerBlock"},
                }
            )
        )

    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
    )

    ws_thread = threading.Thread(
        target=ws.run_forever,
        kwargs=WEBSOCKET_PROXY_KWARGS,
    )
    ws_thread.daemon = True
    ws_thread.start()

    try:
        return height_queue.get(timeout=10)
    except queue.Empty:
        print("Timeout: No block height received")
        return None
    finally:
        ws.close()
