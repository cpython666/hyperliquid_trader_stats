import asyncio
import time

from hyperliquid_trader_stats.plotting.analyze_ls_rate_over_value_pro import analyze_ls_rate
from hyperliquid_trader_stats.services.update_high_win_rate_user_state import update_high_winrate_positions


async def hyper_x_scheduler():
    """
    - 更新高胜率地址持仓状态
    - 统计多空数据
    :return:
    """
    start = time.time()
    await update_high_winrate_positions()
    end = time.time()
    print(f"✅ 更新高胜率地址持仓状态耗时：{end - start:.2f} 秒")
    await analyze_ls_rate()


if __name__ == "__main__":
    asyncio.run(hyper_x_scheduler())
