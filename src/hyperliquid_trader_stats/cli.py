import argparse
import asyncio
import logging
from datetime import datetime


def positive_int(value: str) -> int:
    """解析大于零的整数命令行参数。"""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是大于零的整数。") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("必须是大于零的整数。")
    return parsed


def utc_date(value: str) -> datetime:
    """将 YYYY-MM-DD 命令行参数解析为 UTC 零点。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期格式必须为 YYYY-MM-DD。") from error


class ChineseArgumentParser(argparse.ArgumentParser):
    """使用中文默认帮助文案和分组标题的参数解析器。"""

    def __init__(self, *args, **kwargs):
        add_help = kwargs.pop("add_help", True)
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "可选参数"
        if add_help:
            self.add_argument(
                "-h",
                "--help",
                action="help",
                default=argparse.SUPPRESS,
                help="显示帮助信息并退出。",
            )


def configure_logging(verbose: bool = False):
    """根据命令行参数初始化日志级别和输出格式。"""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


async def init_db_command(args):
    """执行 MongoDB 索引初始化命令。"""
    from hyperliquid_trader_stats.db.collections import init_hyper_x_collections

    await init_hyper_x_collections(include_large_indexes=args.include_large_indexes)


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
    """从指定区块或最新区块开始采集链上交易地址。"""
    from hyperliquid_trader_stats.services.fetch_block_addresses import (
        fetch_and_store_addresses_from_block,
        get_block_height,
    )

    start_height = args.start_height
    if start_height is None:
        start_height = await asyncio.to_thread(get_block_height)
        if start_height is None:
            raise RuntimeError("获取最新区块高度失败，请稍后重试或手动传入起始区块高度。")
        logging.info("未指定起始区块高度，使用最新区块高度：%s", start_height)

    await fetch_and_store_addresses_from_block(
        start_height,
        args.block_count,
        backend="requests" if args.requests else "aiohttp",
        concurrency=args.concurrency,
    )


async def fetch_user_states_command(args):
    """执行用户持仓状态采集命令。"""
    from hyperliquid_trader_stats.services.fetch_and_store_user_state import main

    await main(
        incremental=args.incremental,
        updated_before=args.updated_before,
    )


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

    await process_all_addresses_incrementally(
        incremental=args.incremental,
        stale_days=args.stale_days,
        updated_before=args.updated_before,
    )


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


async def analyze_history_command(args):
    """执行历史分析结果趋势图命令。"""
    from hyperliquid_trader_stats.plotting.analyze_history import visualize_history

    await visualize_history(
        basic=args.basic,
        mode=args.mode,
        export_excel=args.export_excel or None,
        output_dir=args.output_dir,
        show=args.show,
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


async def serve_web_command(args):
    """启动交易员统计 Web 控制台。"""
    import uvicorn

    config = uvicorn.Config(
        "hyperliquid_trader_stats.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


def build_parser():
    """构建 hyper-stats 命令行参数解析器。"""
    parser = ChineseArgumentParser(
        prog="hyper-stats",
        description="采集并分析 Hyperliquid 交易员数据。",
    )
    parser.add_argument("--verbose", action="store_true", help="输出调试级别日志。")

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="命令",
        parser_class=ChineseArgumentParser,
        required=True,
    )

    init_db = subparsers.add_parser(
        "init-db",
        help="初始化 MongoDB 索引。",
        description="创建 HyperX 相关集合需要的 MongoDB 索引。",
    )
    init_db.add_argument(
        "--include-large-indexes",
        action="store_true",
        help="同时创建超大 fills 集合的时间索引，可能耗时较长并占用大量磁盘。",
    )
    init_db.set_defaults(handler=init_db_command)

    leaderboard = subparsers.add_parser(
        "fetch-leaderboard",
        help="采集排行榜地址并写入 MongoDB。",
        description="请求 Hyperliquid 排行榜接口，提取交易员地址并写入地址集合。",
    )
    leaderboard.set_defaults(handler=fetch_leaderboard_command)

    hyperdash = subparsers.add_parser(
        "fetch-hyperdash-top-traders",
        help="采集 Hyperdash 顶级交易员地址。",
        description="读取本地缓存或请求 Hyperdash 顶级交易员接口，筛选有效地址后入库。",
    )
    hyperdash.set_defaults(handler=fetch_hyperdash_top_traders_command)

    block_addresses = subparsers.add_parser(
        "fetch-block-addresses",
        help="从区块中采集账户地址。",
        description="从指定起始区块向前扫描一批 Hyperliquid explorer 区块，并保存其中的用户地址；不传起始高度时自动使用最新区块高度。",
    )
    block_addresses.add_argument(
        "start_height",
        nargs="?",
        type=int,
        default=None,
        help="起始区块高度；省略时自动获取最新区块高度。",
    )
    block_addresses.add_argument(
        "--block-count",
        type=int,
        default=1000,
        help="向前扫描的区块数量，默认 1000。",
    )
    block_addresses.add_argument(
        "--requests",
        action="store_true",
        help="使用 requests 后端采集区块，适合 aiohttp 方式异常时备用。",
    )
    block_addresses.add_argument(
        "--concurrency",
        type=positive_int,
        default=None,
        help="并发请求数量；默认 aiohttp 为 5，requests 为 10。",
    )
    block_addresses.set_defaults(handler=fetch_block_addresses_command)

    states = subparsers.add_parser(
        "fetch-user-states",
        help="采集用户当前持仓状态。",
        description="按增量、全量或更新时间筛选地址，并更新保证金、可提现金额和有效仓位价值。",
    )
    states_mode = states.add_mutually_exclusive_group()
    states_mode.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="仅采集缺少状态的地址（默认）；使用 --no-incremental 可全量刷新。",
    )
    states_mode.add_argument(
        "--updated-before",
        type=utc_date,
        metavar="YYYY-MM-DD",
        help="采集在指定 UTC 日期之前更新或从未更新的地址。",
    )
    states.set_defaults(handler=fetch_user_states_command)

    fills = subparsers.add_parser(
        "fetch-user-fills",
        help="采集用户历史成交。",
        description="按地址批量请求 Hyperliquid userFills，并将成交记录增量写入 MongoDB。",
    )
    fills.add_argument(
        "--limit",
        type=int,
        default=30000,
        help="最多处理的地址数量，默认 30000。",
    )
    fills.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否只处理新增地址；使用 --no-incremental 可按已有摘要全量更新。",
    )
    fills.set_defaults(handler=fetch_user_fills_command)

    compute = subparsers.add_parser(
        "compute-trades",
        help="计算已完成订单和胜率摘要。",
        description="从已保存的 fills 推算已完成订单，计算胜率、盈亏、持仓时长等交易员摘要。",
    )
    compute_mode = compute.add_mutually_exclusive_group()
    compute_mode.add_argument(
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="按 fills 最新时间增量计算；使用 --no-incremental 可重新计算全部地址。",
    )
    compute_mode.add_argument(
        "--stale-days",
        type=positive_int,
        help="重新计算超过指定天数未更新的地址，例如 7。",
    )
    compute_mode.add_argument(
        "--updated-before",
        type=utc_date,
        metavar="YYYY-MM-DD",
        help="重新计算在指定 UTC 日期之前更新的地址。",
    )
    compute.set_defaults(handler=compute_trades_command)

    analyze = subparsers.add_parser(
        "analyze-ls-rate",
        help="分析胜率与多空分布。",
        description="统计高胜率地址的多空人数、仓位价值和入场价值分层分布，可选择保存和绘图。",
    )
    analyze.add_argument(
        "--basic",
        action="store_true",
        help="使用基础分析器，不按入场价值区间细分。",
    )
    analyze.add_argument(
        "--store-result",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否将分析结果写入 MongoDB；使用 --no-store-result 可关闭。",
    )
    analyze.add_argument(
        "--visualize-result",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否生成可视化图表；默认不生成，传入 --visualize-result 开启。",
    )
    analyze.set_defaults(handler=analyze_ls_rate_command)

    history = subparsers.add_parser(
        "analyze-history",
        help="绘制历史分析结果趋势图。",
        description="读取已保存的分析结果，绘制多空人数比和多空价值比随时间变化的折线图。",
    )
    history.add_argument(
        "--basic",
        action="store_true",
        help="使用基础历史图，只绘制总胜率分布并导出 Excel。",
    )
    history.add_argument(
        "--mode",
        choices=["group", "big"],
        default="group",
        help="增强历史图模式：group 按类型分别绘图，big 合并为两张大图；默认 group。",
    )
    history.add_argument(
        "--export-excel",
        default="analyze_result.xlsx",
        help="基础模式导出的 Excel 路径；传空字符串可关闭导出。",
    )
    history.add_argument(
        "--output-dir",
        default=None,
        help="可选的 PNG 保存目录；不传则只显示窗口。",
    )
    history.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否显示 Matplotlib 窗口；使用 --no-show 可只保存文件。",
    )
    history.set_defaults(handler=analyze_history_command)

    update_high_winrate = subparsers.add_parser(
        "update-high-winrate-positions",
        help="刷新高胜率地址持仓状态。",
        description="筛选胜率达到阈值且状态过期的地址，并批量刷新当前持仓状态。",
    )
    update_high_winrate.set_defaults(handler=update_high_winrate_positions_command)

    scheduler = subparsers.add_parser(
        "run-scheduler",
        help="运行内置调度流程。",
        description="执行当前项目内置的高胜率地址状态刷新和胜率多空分布分析流程。",
    )
    scheduler.set_defaults(handler=scheduler_command)

    serve_web = subparsers.add_parser(
        "serve-web",
        help="启动交易员数据筛选 Web 页面。",
        description="使用 FastAPI 启动本地 Web 服务，提供交易员胜率、盈亏和持仓数据的筛选与排序页面。",
    )
    serve_web.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址，默认 127.0.0.1。",
    )
    serve_web.add_argument(
        "--port",
        type=int,
        default=8000,
        help="监听端口，默认 8000。",
    )
    serve_web.add_argument(
        "--reload",
        action="store_true",
        help="开启 uvicorn 自动重载，适合本地开发。",
    )
    serve_web.set_defaults(handler=serve_web_command)

    return parser


def main():
    """解析命令行参数并分发到对应的异步命令处理函数。"""
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    asyncio.run(args.handler(args))


if __name__ == "__main__":
    main()
