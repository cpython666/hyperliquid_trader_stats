'''
https://hyperdash.info/top-traders

https://hyperdash.info/api/hyperdash/top-traders-cached
'''

import asyncio
import json
from pathlib import Path

import aiohttp
from web3 import Web3

from hyperliquid_trader_stats.config import PROJECT_ROOT
from hyperliquid_trader_stats.hyper_x_utils import save_addresses

# 请求最大重试次数
MAX_RETRIES = 5
HYPERDASH_TOP_TRADERS_URL = "https://hyperdash.info/api/hyperdash/top-traders-cached"


async def fetch_and_store_addresses_from_hyperdash_top_traders():
    cache_path = Path(PROJECT_ROOT) / "hyperdash_top_traders.json"
    if cache_path.exists():
        top_traders = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(HYPERDASH_TOP_TRADERS_URL) as response:
                response.raise_for_status()
                top_traders = await response.json()

    addresses = [
        top_trader.get('address')
        for top_trader in top_traders
        if Web3.is_address(top_trader.get('address'))
    ]
    in_addresses = [
        top_trader.get('address')
        for top_trader in top_traders
        if not Web3.is_address(top_trader.get('address'))
    ]

    print(f"✅ 有效地址: {len(addresses)}，❌ 非地址: {len(in_addresses)}")
    if addresses:
        await save_addresses(addresses)

if __name__ == '__main__':
    asyncio.run(fetch_and_store_addresses_from_hyperdash_top_traders())
