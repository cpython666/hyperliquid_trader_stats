import asyncio
import requests
from web3 import Web3
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_addresses_collection
from hyperliquid_trader_stats.hyper_x_utils import save_addresses  # 注意：这个是 async 函数

MAX_RETRIES = 5
CONCURRENCY = 10  # 并发数量控制
SEM = asyncio.Semaphore(CONCURRENCY)


def sync_get_block(height):
    """同步函数，用 requests 请求区块信息"""
    url = 'https://rpc.hyperliquid.xyz/explorer'
    headers = {'Content-Type': 'application/json'}
    json_data = {
        'type': 'blockDetails',
        'height': height,
    }

    for retry in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=json_data, headers=headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"[{height}] ⚠️ 429 Too Many Requests，等待重试...")
                import time
                time.sleep(60)
            else:
                print(f"[{height}] ❌ 请求失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"[{height}] ❌ 请求异常: {e}")
            import time
            time.sleep(3)
    return None


async def get_addresses(height):
    """在线程中请求指定区块详情，并保存其中的有效用户地址。"""
    async with SEM:
        data = await asyncio.to_thread(sync_get_block, height)
        if data is None:
            return

        txs = data.get('blockDetails', {}).get('txs', [])
        addresses = [tx.get('user') for tx in txs if Web3.is_address(tx.get('user'))]
        in_addresses = [tx.get('user') for tx in txs if not Web3.is_address(tx.get('user'))]

        print(f"[{height}] ✅ 有效地址: {len(addresses)}，❌ 非地址: {len(in_addresses)}")

        if addresses:
            await save_addresses(addresses)


async def fetch_and_store_addresses_from_block(start_height: int, block_count: int = 1000):
    """使用 requests 后端从起始区块向前批量扫描地址。"""
    tasks = [
        get_addresses(height)
        for height in range(start_height, start_height - block_count, -1)
    ]
    await asyncio.gather(*tasks)


if __name__ == '__main__':

    # start_block = 659725825
    start_block = 660876453
    asyncio.run(fetch_and_store_addresses_from_block(start_block, 30000))
