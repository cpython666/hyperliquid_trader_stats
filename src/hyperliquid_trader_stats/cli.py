import argparse
import asyncio
import logging


def configure_logging(verbose: bool = False):
    """根据命令行参数初始化日志级别和输出格式。"""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


async def init_db_command(_args):
    """执行 MongoDB 索引初始化命令。"""
    from hyperliquid_trader_stats.db.collections import init_hyper_x_collections

    await init_hyper_x_collections()


async def fetch_leaderboard_command(_args):
    """执行排行榜地址采集命令。"""
    from hyperliquid_trader_stats.services.fetch_and_store_address import main

    await main()


async def fetch_hyperdash_top_traders_command(_args):
    """执行 Hyperdash 顶级交易员地址采集命令。"""
    from hyperliquid_trader_stats.services.fetch_and_store_addresses_from_hyperdash_top_traders import (
        fetch_and_store_addresses_from_hyperdash_top_traders,
    )

    await fetch_and_store_addresses_from_hyperdash_top_traders()


async def fetch_block_addresses_command(args):
    """按指定区块高度范围采集链上交易地址。"""
    if args.requests:
        from hyperliquid_trader_stats.services.fetch_and_store_addresses_from_block_requests import (
            fetch_and_store_addresses_from_block,
        )
    else:
        from hyperliquid_trader_stats.services.fetch_and_store_addresses_from_block import (
            fetch_and_store_addresses_from_block,
        )

    await fetch_and_store_addresses_from_block(args.start_height, args.block_count)


async def fetch_user_states_command(args):
    """执行用户持仓状态采集命令。"""
    from hyperliquid_trader_stats.services.fetch_and_store_user_state import main

    await main(incremental=args.incremental)


async def fetch_user_fills_command(args):
    """执行用户历史成交采集命令。"""
    from hyperliquid_trader_stats.services.fetch_and_store_user_fills import (
        fetch_and_store_user_fills,
    )

    await fetch_and_store_user_fills(limit=args.limit, incremental=args.incremental)


async def compute_trades_command(args):
    """执行已完成订单聚合和胜率摘要计算命令。"""
    from hyperliquid_trader_stats.analytics.compute_complete_trades import (
        process_all_addresses_incrementally,
    )

    await process_all_addresses_incrementally(incremental=args.incremental)


async def analyze_ls_rate_command(args):
    """执行胜率与多空分布分析命令。"""
    if args.basic:
        from hyperliquid_trader_stats.plotting.analyze_ls_rate import analyze_ls_rate
    else:
        from hyperliquid_trader_stats.plotting.analyze_ls_rate_over_value_pro import (
            analyze_ls_rate,
        )

    await analyze_ls_rate(
        store_result=args.store_result,
        visualize_result=args.visualize_result,
    )


async def update_high_winrate_positions_command(_args):
    """刷新高胜率地址的最新持仓状态。"""
    from hyperliquid_trader_stats.services.update_high_win_rate_user_state import (
        update_high_winrate_positions,
    )

    await update_high_winrate_positions()


async def scheduler_command(_args):
    """执行当前项目内置的状态刷新和分析调度流程。"""
    from hyperliquid_trader_stats.services.run_fetch_states_and_analyze import (
        hyper_x_scheduler,
    )

    await hyper_x_scheduler()


def build_parser():
    """构建 hyper-stats 命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="hyper-stats",
        description="Collect and analyze Hyperliquid trader statistics.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create MongoDB indexes.")
    init_db.set_defaults(handler=init_db_command)

    leaderboard = subparsers.add_parser(
        "fetch-leaderboard",
        help="Fetch leaderboard addresses into MongoDB.",
    )
    leaderboard.set_defaults(handler=fetch_leaderboard_command)

    hyperdash = subparsers.add_parser(
        "fetch-hyperdash-top-traders",
        help="Fetch Hyperdash top-trader addresses into MongoDB.",
    )
    hyperdash.set_defaults(handler=fetch_hyperdash_top_traders_command)

    block_addresses = subparsers.add_parser(
        "fetch-block-addresses",
        help="Fetch account addresses from explorer blocks.",
    )
    block_addresses.add_argument("start_height", type=int)
    block_addresses.add_argument("--block-count", type=int, default=1000)
    block_addresses.add_argument(
        "--requests",
        action="store_true",
        help="Use the synchronous requests-backed block fetcher.",
    )
    block_addresses.set_defaults(handler=fetch_block_addresses_command)

    states = subparsers.add_parser(
        "fetch-user-states",
        help="Fetch current account state and position values.",
    )
    states.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    states.set_defaults(handler=fetch_user_states_command)

    fills = subparsers.add_parser(
        "fetch-user-fills",
        help="Fetch user fills into MongoDB.",
    )
    fills.add_argument("--limit", type=int, default=30000)
    fills.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    fills.set_defaults(handler=fetch_user_fills_command)

    compute = subparsers.add_parser(
        "compute-trades",
        help="Compute completed trades and trader summaries.",
    )
    compute.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    compute.set_defaults(handler=compute_trades_command)

    analyze = subparsers.add_parser(
        "analyze-ls-rate",
        help="Analyze win-rate and long/short distribution.",
    )
    analyze.add_argument("--basic", action="store_true", help="Use the basic analyzer.")
    analyze.add_argument(
        "--store-result",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    analyze.add_argument(
        "--visualize-result",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    analyze.set_defaults(handler=analyze_ls_rate_command)

    update_high_winrate = subparsers.add_parser(
        "update-high-winrate-positions",
        help="Refresh user states for high win-rate accounts.",
    )
    update_high_winrate.set_defaults(handler=update_high_winrate_positions_command)

    scheduler = subparsers.add_parser(
        "run-scheduler",
        help="Run the current fetch/analyze scheduler loop.",
    )
    scheduler.set_defaults(handler=scheduler_command)

    return parser


def main():
    """解析命令行参数并分发到对应的异步命令处理函数。"""
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    asyncio.run(args.handler(args))


if __name__ == "__main__":
    main()
