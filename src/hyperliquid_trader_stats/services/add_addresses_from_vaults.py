import asyncio

from hyperliquid_trader_stats.db.collections import web3_hyperliquid_vaults_collection
from hyperliquid_trader_stats.hyper_x_utils import save_addresses


async def get_vaults_followers_users():
    """从金库集合中提取所有 followers 里的用户地址并去重。"""
    user_set = set()
    cursor = web3_hyperliquid_vaults_collection.find({}, {"followers": 1})

    async for doc in cursor:
        followers = doc.get("followers", [])
        if isinstance(followers, list):
            for follower in followers:
                user = follower.get("user")
                if user:
                    user_set.add(user)
        else:
            print(f"⚠️ followers 不是列表: {followers}")

    return user_set


async def add_addresses_from_vaults():
    """将金库 followers 用户地址写入统一地址集合。"""
    addresses = await get_vaults_followers_users()
    await save_addresses(addresses)


if __name__ == '__main__':
    asyncio.run(add_addresses_from_vaults())
