from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from .analysis import (
    SUMMARY_SORT_FIELDS,
    TraderInput,
    analyze_population,
    analyze_trader,
    filter_fills_by_time,
    parse_time_ms,
    sort_results,
)
from .api import HyperliquidClient
from .config import load_env_file
from .discovery import HyperliquidDiscoveryClient, extract_top_trader_addresses, scan_blocks
from .mongo_store import MongoStore
from .storage import ADDRESS_SORT_FIELDS, FileStore, load_addresses, sort_address_records
from .visualize import render_dashboard


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


async def maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


def get_time_bounds(args: argparse.Namespace) -> tuple[int | None, int | None]:
    try:
        start_time_ms = parse_time_ms(getattr(args, "start_date", None))
        end_time_ms = parse_time_ms(getattr(args, "end_date", None), end_of_day=True)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if start_time_ms is not None and end_time_ms is not None and start_time_ms > end_time_ms:
        raise SystemExit("--start-date must be earlier than or equal to --end-date")
    return start_time_ms, end_time_ms


def build_store(args: argparse.Namespace):
    storage = getattr(args, "storage", "file")
    if storage == "mongo":
        return MongoStore(
            uri=getattr(args, "mongo_uri", None),
            db_name=getattr(args, "mongo_db", None),
            report_dir=getattr(args, "data_dir", "data"),
        )
    return FileStore(getattr(args, "data_dir", "data"))


async def resolve_addresses(args: argparse.Namespace, store, *, use_cached_fills: bool = False) -> list[str]:
    addresses = load_addresses(getattr(args, "addresses", None), getattr(args, "address_file", None))
    limit = getattr(args, "limit_addresses", None)
    address_sort = getattr(args, "address_sort", "seen_count")
    address_sort_desc = not getattr(args, "address_sort_asc", False)
    if not addresses and use_cached_fills and isinstance(store, FileStore):
        addresses = [path.stem for path in sorted(store.fills_dir.glob("*.json"))]
    if not addresses:
        addresses = await maybe_await(
            store.load_address_book_addresses(
                limit=limit,
                sort_by=address_sort,
                descending=address_sort_desc,
            )
        )
    if limit:
        addresses = addresses[:limit]
    return addresses


async def fetch_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    addresses = await resolve_addresses(args, store)
    if not addresses:
        raise SystemExit("No addresses provided. Use --addresses, --address-file, or scan-blocks first.")

    start_date_ms, end_date_ms = get_time_bounds(args)
    client = HyperliquidClient(info_url=args.info_url, fills_url=args.fills_url)
    semaphore = asyncio.Semaphore(args.concurrency)

    async with aiohttp.ClientSession() as session:
        async def fetch_one(address: str) -> None:
            async with semaphore:
                incremental_start = await maybe_await(store.last_fill_time(address)) if args.incremental else 0
                start_time = max(incremental_start, start_date_ms or 0)
                logging.info("fetching %s from start_time=%s end_time=%s", address, start_time, end_date_ms)
                state_task = client.fetch_user_state(session, address)
                if end_date_ms is not None and start_time > end_date_ms:
                    fills = []
                    state = await state_task
                else:
                    fills_task = client.fetch_user_fills(
                        session,
                        address,
                        start_time=start_time,
                        end_time=end_date_ms,
                    )
                    fills, state = await asyncio.gather(fills_task, state_task)
                fills = filter_fills_by_time(fills, start_time_ms=start_date_ms, end_time_ms=end_date_ms)
                merged = await maybe_await(store.merge_save_fills(address, fills))
                await maybe_await(
                    store.save_state(
                        address,
                        {
                            "raw": state.raw,
                            "open_position_coins": state.open_position_coins,
                            "effective_position_value": state.effective_position_value,
                        },
                    )
                )
                logging.info("saved %s fills for %s (%s new)", len(merged), address, len(fills))

        await asyncio.gather(*(fetch_one(address) for address in addresses))


async def analyze_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    addresses = await resolve_addresses(args, store, use_cached_fills=True)
    if not addresses:
        raise SystemExit("No cached fills found. Run fetch first or pass --addresses.")

    start_date_ms, end_date_ms = get_time_bounds(args)
    results = []
    for address in addresses:
        fills = await maybe_await(store.load_fills(address))
        fills = filter_fills_by_time(fills, start_time_ms=start_date_ms, end_time_ms=end_date_ms)
        if hasattr(store, "load_state"):
            state = await maybe_await(store.load_state(address))
        else:
            state = {}
            state_path = store.state_path(address)
            if state_path.exists():
                import json

                state = json.loads(state_path.read_text(encoding="utf-8"))
        trader = TraderInput(
            address=address,
            fills=fills,
            open_position_coins=state.get("open_position_coins", []),
            effective_position_value=state.get("effective_position_value"),
        )
        result = analyze_trader(trader)
        await maybe_await(store.save_result(address, result))
        results.append(result)
        logging.info(
            "analyzed %s trades=%s win_rate=%s net_pnl=%s",
            address,
            result["summary"]["total_trades"],
            result["summary"]["win_rate"],
            result["summary"]["net_pnl"],
        )

    results = sort_results(
        results,
        sort_by=getattr(args, "sort_by", "win_rate_wilson_lower_bound"),
        descending=not getattr(args, "sort_asc", False),
    )
    population = analyze_population(results)
    paths = await maybe_await(store.export_reports(results, population))
    dashboard_path = render_dashboard(
        results,
        population,
        Path(args.output),
        sort_by=getattr(args, "sort_by", "win_rate_wilson_lower_bound"),
        sort_desc=not getattr(args, "sort_asc", False),
    )
    logging.info("summary: %s", paths["summary_csv"])
    logging.info("trades: %s", paths["trades_csv"])
    logging.info("dashboard: %s", dashboard_path)


async def run_command(args: argparse.Namespace) -> None:
    await fetch_command(args)
    await analyze_command(args)


async def scan_blocks_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    client = HyperliquidDiscoveryClient(
        explorer_url=args.explorer_url,
        explorer_ws_url=args.explorer_ws_url,
    )
    start_height = args.start_height
    if start_height is None:
        logging.info("fetching latest Hyperliquid explorer block height")
        start_height = await client.get_latest_block_height()
    logging.info("scanning blocks start_height=%s block_count=%s", start_height, args.block_count)

    results = await scan_blocks(
        client,
        start_height=start_height,
        block_count=args.block_count,
        concurrency=args.concurrency,
    )
    addresses = []
    metadata_by_address = {}
    for result in results:
        for address in result.addresses:
            addresses.append(address)
            metadata_by_address[address] = {
                "last_block_height": max(
                    result.height,
                    int(metadata_by_address.get(address, {}).get("last_block_height", 0)),
                )
            }
    stats = await maybe_await(store.upsert_addresses(addresses, source="block_scan", metadata_by_address=metadata_by_address))
    logging.info(
        "address book updated: new=%s updated=%s total=%s files=%s",
        stats["new"],
        stats["updated"],
        stats["total"],
        getattr(store, "address_book_path", "MongoDB"),
    )


async def leaderboard_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    client = HyperliquidDiscoveryClient(leaderboard_url=args.leaderboard_url)
    async with aiohttp.ClientSession() as session:
        addresses = await client.fetch_leaderboard_addresses(session)
    stats = await maybe_await(store.upsert_addresses(addresses, source="leaderboard"))
    logging.info(
        "address book updated from leaderboard: fetched=%s new=%s updated=%s total=%s",
        len(addresses),
        stats["new"],
        stats["updated"],
        stats["total"],
    )


async def hyperdash_top_traders_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    if args.top_traders_file:
        data = json.loads(Path(args.top_traders_file).read_text(encoding="utf-8"))
    else:
        client = HyperliquidDiscoveryClient(hyperdash_top_traders_url=args.hyperdash_url)
        async with aiohttp.ClientSession() as session:
            data = await client.fetch_hyperdash_top_traders(session)

    addresses, metadata_by_address, invalid_count = extract_top_trader_addresses(data)
    stats = await maybe_await(
        store.upsert_addresses(
            addresses,
            source="hyperdash_top_traders",
            metadata_by_address=metadata_by_address,
        )
    )
    logging.info(
        "address book updated from Hyperdash top-traders: fetched=%s invalid=%s new=%s updated=%s total=%s",
        len(addresses),
        invalid_count,
        stats["new"],
        stats["updated"],
        stats["total"],
    )


async def list_addresses_command(args: argparse.Namespace) -> None:
    store = build_store(args)
    records = await maybe_await(store.load_address_records())
    records = sort_address_records(
        records,
        sort_by=args.address_sort,
        descending=not args.address_sort_asc,
    )
    limit = args.limit_addresses or 50
    print(f"total addresses: {len(records)}")
    for record in records[:limit]:
        sources = ",".join(record.get("sources", []))
        print(f"{record.get('ethAddress')} seen={record.get('seen_count', 0)} sources={sources}")


async def init_mongo_command(args: argparse.Namespace) -> None:
    store = MongoStore(uri=args.mongo_uri, db_name=args.mongo_db, report_dir=args.data_dir)
    await store.init_indexes()
    logging.info("MongoDB indexes initialized for legacy HyperX collections")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hyper-stats",
        description="Download Hyperliquid account fills, calculate win rates, and render a dashboard.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs.")

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--addresses", help="Comma-separated addresses.")
    shared.add_argument("--address-file", help="Text/CSV/JSON file containing addresses.")
    shared.add_argument("--data-dir", default="data", help="Local cache directory.")
    shared.add_argument("--output", default="data/reports/dashboard.html", help="Dashboard HTML output path.")
    shared.add_argument("--limit-addresses", type=int, help="Limit addresses loaded from args, file, or address book.")
    shared.add_argument("--storage", choices=["file", "mongo"], default="file", help="Storage backend.")
    shared.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    shared.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    shared.add_argument("--start-date", help="Inclusive fill start date/time, e.g. 2025-01-01 or 2025-01-01T00:00:00Z.")
    shared.add_argument("--end-date", help="Inclusive fill end date/time. A date-only value includes the whole UTC day.")
    shared.add_argument(
        "--address-sort",
        choices=sorted(ADDRESS_SORT_FIELDS),
        default="seen_count",
        help="Sort field when loading addresses from the address book.",
    )
    shared.add_argument("--address-sort-asc", action="store_true", help="Sort address book ascending instead of descending.")

    fetch_shared = argparse.ArgumentParser(add_help=False)
    fetch_shared.add_argument("--info-url", default="https://api.hyperliquid.xyz/info")
    fetch_shared.add_argument("--fills-url", default="https://api-ui.hyperliquid.xyz/info")
    fetch_shared.add_argument("--concurrency", type=int, default=3)
    fetch_shared.add_argument("--incremental", action=argparse.BooleanOptionalAction, default=True)

    analyze_shared = argparse.ArgumentParser(add_help=False)
    analyze_shared.add_argument(
        "--sort-by",
        choices=sorted(SUMMARY_SORT_FIELDS),
        default="win_rate_wilson_lower_bound",
        help="Sort field for summary.csv and dashboard.",
    )
    analyze_shared.add_argument("--sort-asc", action="store_true", help="Sort analysis results ascending instead of descending.")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("fetch", parents=[shared, fetch_shared], help="Download fills and current positions.")
    subparsers.add_parser("analyze", parents=[shared, analyze_shared], help="Analyze cached fills and render reports.")
    subparsers.add_parser("run", parents=[shared, fetch_shared, analyze_shared], help="Fetch, analyze, and render reports.")
    scan_parser = subparsers.add_parser("scan-blocks", help="Scan Hyperliquid explorer blocks and add user accounts to the local address book.")
    scan_parser.add_argument("--data-dir", default="data", help="Local cache directory.")
    scan_parser.add_argument("--storage", choices=["file", "mongo"], default="file", help="Storage backend.")
    scan_parser.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    scan_parser.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    scan_parser.add_argument("--start-height", type=int, help="Start block height. Defaults to latest explorer block.")
    scan_parser.add_argument("--block-count", type=int, default=1000, help="Number of blocks to scan backwards.")
    scan_parser.add_argument("--concurrency", type=int, default=5, help="Concurrent block requests.")
    scan_parser.add_argument("--explorer-url", default="https://rpc.hyperliquid.xyz/explorer")
    scan_parser.add_argument("--explorer-ws-url", default="wss://rpc.hyperliquid.xyz/ws")

    leaderboard_parser = subparsers.add_parser("discover-leaderboard", help="Import Hyperliquid leaderboard accounts into the local address book.")
    leaderboard_parser.add_argument("--data-dir", default="data", help="Local cache directory.")
    leaderboard_parser.add_argument("--storage", choices=["file", "mongo"], default="file", help="Storage backend.")
    leaderboard_parser.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    leaderboard_parser.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    leaderboard_parser.add_argument("--leaderboard-url", default="https://stats-data.hyperliquid.xyz/Mainnet/leaderboard")

    hyperdash_parser = subparsers.add_parser("discover-hyperdash-top-traders", help="Import Hyperdash top-trader accounts into the address book.")
    hyperdash_parser.add_argument("--data-dir", default="data", help="Local cache directory.")
    hyperdash_parser.add_argument("--storage", choices=["file", "mongo"], default="file", help="Storage backend.")
    hyperdash_parser.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    hyperdash_parser.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    hyperdash_parser.add_argument("--top-traders-file", help="Path to a Hyperdash top-traders JSON file.")
    hyperdash_parser.add_argument("--hyperdash-url", default="https://hyperdash.info/api/hyperdash/top-traders-cached")

    addresses_parser = subparsers.add_parser("addresses", help="List accounts currently stored in the local address book.")
    addresses_parser.add_argument("--data-dir", default="data", help="Local cache directory.")
    addresses_parser.add_argument("--storage", choices=["file", "mongo"], default="file", help="Storage backend.")
    addresses_parser.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    addresses_parser.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    addresses_parser.add_argument("--limit-addresses", type=int, help="Maximum rows to print.")
    addresses_parser.add_argument(
        "--address-sort",
        choices=sorted(ADDRESS_SORT_FIELDS),
        default="seen_count",
        help="Sort field for printed address records.",
    )
    addresses_parser.add_argument("--address-sort-asc", action="store_true", help="Sort address records ascending instead of descending.")

    init_mongo_parser = subparsers.add_parser("init-mongo", help="Create indexes for the legacy StarDreamAPI HyperX MongoDB collections.")
    init_mongo_parser.add_argument("--data-dir", default="data", help="Local report directory.")
    init_mongo_parser.add_argument("--mongo-uri", help="MongoDB URI. Defaults to MONGODB_URL.")
    init_mongo_parser.add_argument("--mongo-db", help="MongoDB database name. Defaults to MONGODB_DB_NAME.")
    return parser


def main() -> None:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    if args.command == "fetch":
        asyncio.run(fetch_command(args))
    elif args.command == "analyze":
        asyncio.run(analyze_command(args))
    elif args.command == "run":
        asyncio.run(run_command(args))
    elif args.command == "scan-blocks":
        asyncio.run(scan_blocks_command(args))
    elif args.command == "discover-leaderboard":
        asyncio.run(leaderboard_command(args))
    elif args.command == "discover-hyperdash-top-traders":
        asyncio.run(hyperdash_top_traders_command(args))
    elif args.command == "addresses":
        asyncio.run(list_addresses_command(args))
    elif args.command == "init-mongo":
        asyncio.run(init_mongo_command(args))
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
