import asyncio
import aiohttp
from web3 import Web3
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_hyper_x_addresses_collection
from hyperliquid_trader_stats.hyper_x_utils import save_addresses

# 控制并发请求数，避免触发 429
SEM = asyncio.Semaphore(5)  # 同时最多 5 个请求，可调大/小

# 请求最大重试次数
MAX_RETRIES = 5


async def get_addresses(session, height):
    headers = {
        'Content-Type': 'application/json',
    }

    json_data = {
        'type': 'blockDetails',
        'height': height,
    }

    retry = 0
    while retry < MAX_RETRIES:
        async with SEM:
            try:
                async with session.post(
                    'https://rpc.hyperliquid.xyz/explorer',
                    json=json_data,
                    headers=headers,
                    timeout=5
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        # print(data)
                        txs = data.get('blockDetails', {}).get('txs', [])

                        addresses = [tx.get('user') for tx in txs if Web3.is_address(tx.get('user'))]
                        in_addresses = [tx.get('user') for tx in txs if not Web3.is_address(tx.get('user'))]

                        print(f"[{height}] ✅ 有效地址: {len(addresses)}，❌ 非地址: {len(in_addresses)}")
                        if addresses:
                            await save_addresses(addresses)
                        return

                    elif response.status == 429:
                        print(f"[{height}] ⚠️ 429 Too Many Requests，等待 61 秒再试...")
                        await asyncio.sleep(61)
                        retry += 1
                    else:
                        print(f"[{height}] ❌ 请求失败，状态码: {response.status}")
                        return
            except Exception as e:
                print(f"[{height}] ❌ 请求异常: {e}")
                await asyncio.sleep(3)
                retry += 1


async def fetch_and_store_addresses_from_block(start_height: int, block_count: int = 1000):
    async with aiohttp.ClientSession() as session:
        # await get_addresses(session, 651837701)

        tasks = [
            get_addresses(session, height)
            for height in range(start_height, start_height - block_count, -1)
        ]
        await asyncio.gather(*tasks)
import websocket
import json
import threading
import queue

def get_block_height():
    """获取最新区块高度并返回"""
    height_queue = queue.Queue()  # 用于传递高度

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, list) and data:
                height = data[0].get('height')
                if height:
                    height_queue.put(height)  # 将高度放入队列
                    ws.close()  # 获取高度后关闭连接

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")

    def on_error(ws, error):
        print(f"Error: {error}")
        height_queue.put(None)  # 发生错误时放入None
        ws.close()

    def on_open(ws):
        print("WebSocket opened")
        ws.send(json.dumps({
            "method": "subscribe",
            "subscription": {"type": "explorerBlock"}
        }))

    ws_url = "wss://rpc.hyperliquid.xyz/ws"  # Hypurrscan的可能端点
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open
    )

    # 在新线程中运行WebSocket，避免阻塞
    ws_thread = threading.Thread(target=ws.run_forever)
    ws_thread.daemon = True  # 设置为守护线程
    ws_thread.start()

    try:
        # 等待队列中的高度，最多等待10秒
        height = height_queue.get(timeout=10)
        return height
    except queue.Empty:
        print("Timeout: No block height received")
        return None
    finally:
        ws.close()  # 确保连接关闭

if __name__ == '__main__':
    # start_block = 651879309
    start_block = get_block_height()
    print(start_block)

    asyncio.run(fetch_and_store_addresses_from_block(start_block, 10000))
