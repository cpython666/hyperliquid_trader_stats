from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .storage import FileStore, safe_address, sort_address_records

ADDRESSES_COLLECTION = "web3_hyperliquid_hyper_x_addresses"
USER_FILLS_COLLECTION = "web3_hyperliquid_hyper_x_user_fills"
USER_FILLS_SUMMARY_COLLECTION = "web3_hyperliquid_hyper_x_user_fills_summary"
COMPLETED_TRADES_COLLECTION = "web3_hyperliquid_hyper_x_completed_trades"
TRADE_SUMMARY_COLLECTION = "web3_hyperliquid_hyper_x_trade_summary"
ANALYZE_RESULT_COLLECTION = "web3_hyperliquid_hyper_x_analyze_result"


def _import_mongo_deps():
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from pymongo import ASCENDING, DESCENDING, UpdateOne
    except ImportError as exc:
        raise RuntimeError('MongoDB support is optional. Install it with: pip install -e ".[mongo]"') from exc
    return AsyncIOMotorClient, ASCENDING, DESCENDING, UpdateOne


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _open_position_coins_from_state(state: dict[str, Any] | None) -> list[str]:
    if not state:
        return []
    coins = []
    for item in state.get("assetPositions", []) or []:
        position = item.get("position", {}) if isinstance(item, dict) else {}
        coin = position.get("coin")
        if coin:
            coins.append(str(coin))
    return coins


def _completed_trade_payload(address: str, result: dict[str, Any]) -> dict[str, Any]:
    summary = result["summary"]
    trades = result["trades"]
    per_asset = result["per_asset"]

    long_pnl = round(sum(trade["closed_pnl"] for trade in trades if trade["direction"] == "Long"), 2)
    short_pnl = round(sum(trade["closed_pnl"] for trade in trades if trade["direction"] == "Short"), 2)
    entry_value_summary = {}
    for threshold, key in [
        (1e4, "win_rate_over_1w"),
        (1e5, "win_rate_over_10w"),
        (1e6, "win_rate_over_100w"),
        (1e7, "win_rate_over_1000w"),
    ]:
        filtered = [trade for trade in trades if trade.get("entry_value", 0) >= threshold]
        total = len(filtered)
        wins = sum(1 for trade in filtered if trade["net_pnl"] > 0)
        win_rate = round(wins / total * 100, 2) if total else 0.0
        entry_value_summary[key] = {
            "total_trades": total,
            "winning_trades": wins,
            "win_rate": win_rate,
        }

    return {
        "ethAddress": address,
        "completed_trades": trades,
        "completed_trade_pnl": {
            "pnl": summary["gross_pnl"],
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "fees": summary["fees"],
            "net": summary["net_pnl"],
        },
        "duration_stats": {
            "avg_duration_minutes": summary["avg_duration_minutes"],
            "median_duration_minutes": summary["median_duration_minutes"],
            "q1_duration_minutes": 0.0,
            "q3_duration_minutes": 0.0,
        },
        "stats_per_asset": {
            coin: {
                "total_pnL": stats["total_pnl"],
                "total_fees": stats["fees"],
                "net_pnl": stats["net_pnl"],
                "number_of_trades": stats["trades"],
            }
            for coin, stats in per_asset.items()
        },
        "total_trades": summary["total_trades"],
        "winning_trades": summary["winning_trades"],
        "win_rate": summary["win_rate"],
        "win_rate_score": summary["win_rate_score"],
        "win_rate_wilson_lower_bound": summary["win_rate_wilson_lower_bound"],
        "win_rate_long": summary["win_rate_long"],
        "win_rate_short": summary["win_rate_short"],
        "entry_value_summary": entry_value_summary,
        "analysis_result_v2": result,
        "updated_at": _utcnow(),
    }


class MongoStore:
    """Read/write the legacy StarDreamAPI HyperX MongoDB collections."""

    def __init__(self, *, uri: str | None = None, db_name: str | None = None, report_dir: str = "data") -> None:
        uri = uri or os.getenv("MONGODB_URL")
        db_name = db_name or os.getenv("MONGODB_DB_NAME")
        if not uri or not db_name:
            raise RuntimeError("MongoDB storage needs MONGODB_URL and MONGODB_DB_NAME, or --mongo-uri/--mongo-db.")

        AsyncIOMotorClient, _, _, _ = _import_mongo_deps()
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.addresses = self.db[ADDRESSES_COLLECTION]
        self.user_fills = self.db[USER_FILLS_COLLECTION]
        self.user_fills_summary = self.db[USER_FILLS_SUMMARY_COLLECTION]
        self.completed_trades = self.db[COMPLETED_TRADES_COLLECTION]
        self.trade_summary = self.db[TRADE_SUMMARY_COLLECTION]
        self.analyze_result = self.db[ANALYZE_RESULT_COLLECTION]
        self.report_store = FileStore(report_dir)

    async def init_indexes(self) -> None:
        _, ASCENDING, DESCENDING, _ = _import_mongo_deps()
        await self.addresses.create_index([("ethAddress", ASCENDING)], unique=True, name="unique_eth_address")
        await self.user_fills.create_index(
            [("ethAddress", ASCENDING), ("tid", ASCENDING)],
            unique=True,
            name="unique_eth_address_tid",
        )
        await self.user_fills.create_index([("ethAddress", ASCENDING), ("time", DESCENDING)], name="fills_address_time")
        await self.user_fills_summary.create_index([("ethAddress", ASCENDING)], unique=True, name="unique_eth_address")
        await self.completed_trades.create_index([("ethAddress", ASCENDING)], unique=True, name="unique_eth_address")
        await self.trade_summary.create_index([("ethAddress", ASCENDING)], unique=True, name="unique_eth_address")

    async def load_address_records(self) -> list[dict[str, Any]]:
        cursor = self.addresses.find({}, {"_id": 0})
        return [doc async for doc in cursor]

    async def upsert_addresses(
        self,
        addresses: list[str] | set[str],
        *,
        source: str,
        metadata_by_address: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        _, _, _, UpdateOne = _import_mongo_deps()
        metadata_by_address = metadata_by_address or {}
        counts = Counter(safe_address(address) for address in addresses if address)
        counts.pop("", None)
        now = _utcnow()
        operations = []

        for address, seen_count in counts.items():
            metadata = metadata_by_address.get(address, {})
            max_fields = {}
            if metadata.get("last_block_height") is not None:
                max_fields["last_block_height"] = int(metadata["last_block_height"])
                metadata = {key: value for key, value in metadata.items() if key != "last_block_height"}
            set_fields = {
                "ethAddress": address,
                "source": source,
                "last_source": source,
                "last_seen_at": now,
                "updated_at": now,
                **metadata,
            }
            update_doc = {
                "$set": set_fields,
                "$setOnInsert": {"created_at": now, "createdAt": now, "first_seen_at": now},
                "$addToSet": {"sources": source},
                "$inc": {"seen_count": seen_count},
            }
            if max_fields:
                update_doc["$max"] = max_fields
            operations.append(
                UpdateOne(
                    {"ethAddress": address},
                    update_doc,
                    upsert=True,
                )
            )

        if not operations:
            return {"new": 0, "updated": 0, "total": await self.addresses.count_documents({})}

        result = await self.addresses.bulk_write(operations, ordered=False)
        total = await self.addresses.count_documents({})
        return {
            "new": len(result.upserted_ids),
            "updated": result.matched_count,
            "total": total,
        }

    async def load_address_book_addresses(
        self,
        *,
        limit: int | None = None,
        sort_by: str = "seen_count",
        descending: bool = True,
    ) -> list[str]:
        records = await self.load_address_records()
        records = sort_address_records(records, sort_by=sort_by, descending=descending)
        addresses = [record["ethAddress"] for record in records if record.get("ethAddress")]
        return addresses[:limit] if limit else addresses

    async def load_fills(self, address: str) -> list[dict[str, Any]]:
        cursor = self.user_fills.find({"ethAddress": address}, {"fill": 1, "_id": 0}).sort("time", 1)
        fills = []
        async for doc in cursor:
            fill = doc.get("fill")
            if isinstance(fill, dict):
                fills.append(fill)
        return fills

    async def merge_save_fills(self, address: str, new_fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _, _, _, UpdateOne = _import_mongo_deps()
        if not new_fills:
            return await self.load_fills(address)

        now = _utcnow()
        operations = []
        for fill in new_fills:
            tid = fill.get("tid")
            if tid is None:
                continue
            operations.append(
                UpdateOne(
                    {"ethAddress": address, "tid": tid},
                    {
                        "$set": {
                            "ethAddress": address,
                            "tid": tid,
                            "fill": fill,
                            "coin": fill.get("coin"),
                            "time": fill.get("time"),
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            await self.user_fills.bulk_write(operations, ordered=False)
            latest_time = max((fill.get("time") or 0 for fill in new_fills), default=0)
            if latest_time:
                await self.user_fills_summary.update_one(
                    {"ethAddress": address},
                    {"$set": {"ethAddress": address, "lastTime": latest_time, "updatedAt": now}},
                    upsert=True,
                )
        return await self.load_fills(address)

    async def last_fill_time(self, address: str) -> int:
        summary = await self.user_fills_summary.find_one({"ethAddress": address}, {"lastTime": 1, "_id": 0})
        if summary and summary.get("lastTime"):
            return int(summary["lastTime"])
        last_fill = await self.user_fills.find_one(
            {"ethAddress": address},
            {"time": 1, "_id": 0},
            sort=[("time", -1)],
        )
        return int(last_fill["time"]) if last_fill and last_fill.get("time") else 0

    async def save_state(self, address: str, state: dict[str, Any]) -> None:
        raw = state.get("raw", {})
        await self.addresses.update_one(
            {"ethAddress": address},
            {
                "$set": {
                    "ethAddress": address,
                    "state": raw,
                    "marginSummary": raw.get("marginSummary"),
                    "crossMarginSummary": raw.get("crossMarginSummary"),
                    "withdrawable": raw.get("withdrawable"),
                    "open_position_coins": state.get("open_position_coins", []),
                    "effective_position_value": state.get("effective_position_value"),
                    "updated_at": _utcnow(),
                },
                "$setOnInsert": {"createdAt": _utcnow(), "source": "manual_fetch"},
            },
            upsert=True,
        )

    async def load_state(self, address: str) -> dict[str, Any]:
        doc = await self.addresses.find_one({"ethAddress": address}, {"_id": 0})
        if not doc:
            return {}
        raw = doc.get("state", {})
        return {
            "raw": raw,
            "open_position_coins": doc.get("open_position_coins") or _open_position_coins_from_state(raw),
            "effective_position_value": doc.get("effective_position_value"),
        }

    async def save_result(self, address: str, result: dict[str, Any]) -> None:
        payload = _completed_trade_payload(address, result)
        await self.completed_trades.update_one({"ethAddress": address}, {"$set": payload}, upsert=True)

    async def export_reports(self, results: list[dict[str, Any]], population: dict[str, Any]):
        return self.report_store.export_reports(results, population)
