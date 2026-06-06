import asyncio
import aiohttp
import logging

from hyperliquid_trader_stats.hyper_x_utils import save_addresses

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")]
)
logger = logging.getLogger(__name__)

LEADERBOARD_API = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


async def fetch_leaderboard_data(session: aiohttp.ClientSession, retries=3, timeout=10):
    for attempt in range(retries):
        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with session.get(LEADERBOARD_API, timeout=client_timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    rows = data.get("leaderboardRows", [])
                    logger.info(f"获取到 {len(rows)} 条排行榜数据")
                    return rows
                else:
                    logger.warning(f"第 {attempt + 1} 次请求失败，状态码: {response.status}")
        except Exception as e:
            logger.warning(f"第 {attempt + 1} 次请求异常: {e}")
        await asyncio.sleep(2)
    logger.error("获取排行榜数据失败")
    return []


async def main():
    try:
        async with aiohttp.ClientSession() as session:
            rows = await fetch_leaderboard_data(session)
            addresses = [row["ethAddress"] for row in rows]
            await save_addresses(addresses)
    except Exception as e:
        logger.error(f"主函数发生异常: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
