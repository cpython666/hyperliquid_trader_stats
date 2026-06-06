import asyncio
import aiohttp
import logging
import time
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from hyperliquid_trader_stats.db.collections import web3_hyperliquid_vaults_collection

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# API URL
DETAILS_API_URL = "https://api.hyperliquid.xyz/info"

# MongoDB 集合
vaults_collection = web3_hyperliquid_vaults_collection

# 限流配置
MAX_CONCURRENT_REQUESTS = 5  # 最大并发请求数
REQUEST_DELAY = 0.2  # 每个请求之间的最小间隔（秒）
RETRY_DELAY = 60  # 遇到 429 错误后的睡眠时间（秒）


class RateLimitException(Exception):
    """自定义异常，用于处理 HTTP 429 错误"""

    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type(RateLimitException),
    before_sleep=lambda retry_state: logger.info(
        f"遇到 429 错误，暂停 {RETRY_DELAY} 秒后重试 (第 {retry_state.attempt_number}/3 次)"
    ),
)
async def fetch_vault_details(
    vault_address: str, user_address: str = "0xB1218f99E81548C719D9b49F1355b72f3eaA8fE9"
):
    """异步获取单个金库的详情数据，处理 429 限流"""
    headers = {"Content-Type": "application/json"}
    json_data = {
        "type": "vaultDetails",
        "user": user_address,
        "vaultAddress": vault_address,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DETAILS_API_URL, headers=headers, json=json_data
            ) as response:
                if response.status == 429:
                    raise RateLimitException(f"API 限流: {vault_address}")
                if response.status != 200:
                    logger.error(
                        f"详情 API 请求失败 {vault_address}: HTTP {response.status}"
                    )
                    return None
                data = await response.json()
                logger.info(f"成功获取金库 {vault_address} 详情数据")
                return data
    except RateLimitException:
        raise  # 交给 tenacity 处理
    except Exception as e:
        logger.error(f"获取金库 {vault_address} 详情出错: {str(e)}")
        return None


async def store_details_to_mongodb(data):
    """逐个将金库详情数据存储到 MongoDB，合并到现有文档"""
    if not data:
        logger.warning("无详情数据可存储")
        return

    vault_address = data.get("vaultAddress")
    if not vault_address:
        logger.warning("详情数据缺少 vaultAddress，跳过")
        return

    try:
        vault_doc = {
            "vaultAddress": vault_address,
            "last_updated_details": int(time.time()),
        } | data
        result = await vaults_collection.update_one(
            {"vaultAddress": vault_address}, {"$set": vault_doc}, upsert=True
        )
        if result.matched_count > 0:
            logger.info(f"更新金库 {vault_address} 详情数据")
        else:
            logger.info(f"插入金库 {vault_address} 详情数据")
    except Exception as e:
        logger.error(f"存储金库 {vault_address} 详情数据到 MongoDB 出错: {str(e)}")


async def fetch_and_store_vault_details(vault_address, semaphore):
    """获取单个金库详情并立即存储"""
    async with semaphore:
        data = await fetch_vault_details(vault_address)
        if data:
            data["vaultAddress"] = vault_address  # 确保 vaultAddress 字段一致
            await store_details_to_mongodb(data)
        await asyncio.sleep(REQUEST_DELAY)  # 添加请求间隔


async def main(
    top_n: int = 100, sort_by: str = "tvl", only_missing_details: bool = True
):
    """主函数：查询排行榜数据，按排序取前 N 个金库，获取并存储详情"""
    logger.info(f"开始更新 Hyperliquid 金库详情数据 (top_n={top_n}, sort_by={sort_by})")

    # 查询 MongoDB 中的排行榜数据
    if only_missing_details:
        query = {"description": {"$exists": False}}
    else:
        query = {}
    projection = {"vaultAddress": 1}  # 仅查询 vaultAddress

    cursor = vaults_collection.find(query, projection=projection)
    ranking_data = await cursor.to_list(length=None)

    if not ranking_data:
        logger.warning("MongoDB 中无符合条件的排行榜数据")
        return

    logger.info(f"查询到 {len(ranking_data)} 条排行榜数据")

    # 按指定字段排序
    if sort_by == "tvl":
        sorted_vaults = sorted(
            ranking_data, key=lambda x: float(x.get("tvl", 0)), reverse=True
        )
    elif sort_by == "profit":
        sorted_vaults = sorted(
            ranking_data,
            key=lambda x: float(
                x.get("pnls", [[], []])[3][1][-1]
                if x.get("pnls") and len(x.get("pnls")) > 3
                else 0
            ),
            reverse=True,
        )
    else:
        logger.error(f"不支持的排序字段: {sort_by}")
        return

    # 取前 N 个金库
    top_vaults = sorted_vaults[:top_n]
    logger.info(f"选取前 {top_n} 个金库，按 {sort_by} 排序")

    if not top_vaults:
        logger.warning("无金库需要更新详情")
        return

    print("yes") if "0xf967239debef10dbc78e9bbbb2d8a16b72a614eb" in [
        value["vaultAddress"] for value in top_vaults
    ] else print("no")

    # 使用信号量控制请求并发
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # 创建并发任务
    tasks = [
        fetch_and_store_vault_details(vault.get("vaultAddress"), semaphore)
        for vault in top_vaults
    ]

    # 并发执行所有任务
    await asyncio.gather(*tasks)

    logger.info("金库详情数据处理完成")


if __name__ == "__main__":
    # asyncio.run(main(top_n=1000, sort_by="profit", only_missing_details=True))
    # asyncio.run(main(top_n=1000, sort_by="tvl", only_missing_details=True))
    asyncio.run(main(top_n=1000, sort_by="tvl", only_missing_details=False))
