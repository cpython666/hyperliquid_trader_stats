from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from math import ceil
from typing import Any, Optional

from hyperliquid_trader_stats.db.collections import (
    web3_hyperliquid_hyper_x_analyze_result_collection,
    web3_hyperliquid_hyper_x_addresses_collection,
    web3_hyperliquid_hyper_x_completed_trades_collection,
)


SORT_FIELDS = {
    "win_rate": "win_rate",
    "win_rate_score": "win_rate_score",
    "wilson": "win_rate_wilson_lower_bound",
    "total_trades": "total_trades",
    "net_pnl": "completed_trade_pnl.net",
    "pnl": "completed_trade_pnl.pnl",
    "fees": "completed_trade_pnl.fees",
    "avg_duration": "duration_stats.avg_duration_minutes",
    "updated_at": "updated_at",
    "processed_through": "processedThroughTime",
    "position_value": "effective_position_value",
    "account_value": "account_value",
}

JOINED_SORT_FIELDS = {"position_value", "account_value"}
ADDRESS_SORT_FIELDS = {
    "position_value": "effective_position_value",
    "account_value": "marginSummary.accountValue",
}
TOTAL_TRADES_RANK_INDEX = "total_trades_rank_fields"

ENTRY_VALUE_FIELDS = {
    "1w": "entry_value_summary.win_rate_over_1w.win_rate",
    "10w": "entry_value_summary.win_rate_over_10w.win_rate",
    "100w": "entry_value_summary.win_rate_over_100w.win_rate",
    "1000w": "entry_value_summary.win_rate_over_1000w.win_rate",
}


def _build_completed_match(filters: dict[str, Any]) -> dict[str, Any]:
    completed_match: dict[str, Any] = {}
    search = filters.get("search")
    if search:
        search_term = search.strip()
        if search_term.startswith("0x") and len(search_term) == 42:
            completed_match["ethAddress"] = search_term
        else:
            completed_match["ethAddress"] = {
                "$regex": re.escape(search_term),
                "$options": "i",
            }

    _number_filter(
        completed_match,
        "win_rate",
        filters.get("min_win_rate"),
        filters.get("max_win_rate"),
    )
    _number_filter(
        completed_match,
        "total_trades",
        filters.get("min_total_trades"),
        filters.get("max_total_trades"),
    )
    _number_filter(
        completed_match,
        "completed_trade_pnl.net",
        filters.get("min_net_pnl"),
        filters.get("max_net_pnl"),
    )
    _datetime_filter(
        completed_match,
        "updated_at",
        filters.get("updated_after"),
        filters.get("updated_before"),
    )

    entry_win_rate_field = ENTRY_VALUE_FIELDS.get(
        filters.get("entry_value_tier", "all")
    )
    min_entry_win_rate = filters.get("min_entry_win_rate")
    if entry_win_rate_field and min_entry_win_rate is not None:
        _number_filter(
            completed_match,
            entry_win_rate_field,
            min_entry_win_rate,
            None,
        )
    return completed_match


def _build_joined_match(filters: dict[str, Any]) -> dict[str, Any]:
    joined_match: dict[str, Any] = {}
    _number_filter(
        joined_match,
        "effective_position_value",
        filters.get("min_position_value"),
        filters.get("max_position_value"),
    )

    position_direction = filters.get("position_direction", "any")
    if position_direction == "long":
        bounds = dict(joined_match.get("effective_position_value", {}))
        if "$gte" in bounds:
            bounds["$gt"] = max(bounds.pop("$gte"), 0)
        else:
            bounds["$gt"] = 0
        joined_match["effective_position_value"] = bounds
    elif position_direction == "short":
        bounds = dict(joined_match.get("effective_position_value", {}))
        if "$lte" in bounds:
            bounds["$lt"] = min(bounds.pop("$lte"), 0)
        else:
            bounds["$lt"] = 0
        joined_match["effective_position_value"] = bounds
    elif position_direction == "flat":
        joined_match["effective_position_value"] = 0
    elif position_direction == "unknown":
        joined_match["effective_position_value"] = None
    return joined_match


def _number_filter(
    query: dict[str, Any],
    field: str,
    min_value: Optional[float],
    max_value: Optional[float],
) -> None:
    bounds: dict[str, float] = {}
    if min_value is not None:
        bounds["$gte"] = min_value
    if max_value is not None:
        bounds["$lte"] = max_value
    if bounds:
        query[field] = bounds


def _datetime_filter(
    query: dict[str, Any],
    field: str,
    start: Optional[datetime],
    end: Optional[datetime],
) -> None:
    bounds: dict[str, datetime] = {}
    if start is not None:
        bounds["$gte"] = _as_utc_naive(start)
    if end is not None:
        bounds["$lte"] = _as_utc_naive(end)
    if bounds:
        query[field] = bounds


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _build_address_first_trader_pipeline(
    *,
    page: int,
    page_size: int,
    completed_match: dict[str, Any],
    joined_match: dict[str, Any],
    sort_by: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    """Build an index-friendly pipeline starting from account state."""
    sort_value = 1 if sort_dir == "asc" else -1
    skip = (page - 1) * page_size
    pipeline: list[dict[str, Any]] = []

    if joined_match:
        pipeline.append({"$match": joined_match})

    address_sort_field = ADDRESS_SORT_FIELDS.get(sort_by)
    if address_sort_field:
        pipeline.append(
            {
                "$sort": {
                    address_sort_field: sort_value,
                    "ethAddress": -sort_value,
                }
            }
        )

    pipeline.append(
        {
            "$project": {
                "_id": 0,
                "ethAddress": 1,
                "effective_position_value": 1,
                "account_value": "$marginSummary.accountValue",
                "withdrawable": 1,
                "state_updated_at": "$updated_at",
            }
        }
    )

    lookup_pipeline: list[dict[str, Any]] = []
    if completed_match:
        lookup_pipeline.append({"$match": completed_match})
    lookup_pipeline.append({"$project": _trader_projection()})
    item_pipeline: list[dict[str, Any]] = [
        {
            "$lookup": {
                "from": web3_hyperliquid_hyper_x_completed_trades_collection.name,
                "localField": "ethAddress",
                "foreignField": "ethAddress",
                "pipeline": lookup_pipeline,
                "as": "completed",
            }
        },
        {"$unwind": "$completed"},
        {
            "$replaceRoot": {
                "newRoot": {
                    "$mergeObjects": [
                        "$completed",
                        {
                            "effective_position_value": "$effective_position_value",
                            "account_value": "$account_value",
                            "withdrawable": "$withdrawable",
                            "state_updated_at": "$state_updated_at",
                        },
                    ]
                }
            }
        },
    ]

    if not address_sort_field:
        sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["win_rate_score"])
        item_pipeline.append(
            {"$sort": {sort_field: sort_value, "ethAddress": -sort_value}}
        )

    item_pipeline.extend(
        [
            {"$skip": skip},
            {"$limit": page_size},
            _project_trader_row(),
        ]
    )
    pipeline.append(
        {
            "$facet": {
                "items": item_pipeline,
                "metadata": [{"$count": "total"}],
            }
        }
    )
    return pipeline


def _build_completed_first_joined_pipeline(
    *,
    page: int,
    page_size: int,
    completed_match: dict[str, Any],
    joined_match: dict[str, Any],
    sort_by: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    """Build a joined-filter pipeline that preserves completed-trade sorting."""
    sort_value = 1 if sort_dir == "asc" else -1
    sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["win_rate_score"])
    skip = (page - 1) * page_size
    pipeline: list[dict[str, Any]] = []
    if completed_match:
        pipeline.append({"$match": completed_match})
    pipeline.extend(
        [
            {"$sort": {sort_field: sort_value, "ethAddress": -sort_value}},
            {"$project": _trader_projection()},
        ]
    )

    address_lookup_pipeline: list[dict[str, Any]] = []
    if joined_match:
        address_lookup_pipeline.append({"$match": joined_match})
    address_lookup_pipeline.append({"$project": _address_state_projection()})
    item_pipeline = [
        {
            "$lookup": {
                "from": web3_hyperliquid_hyper_x_addresses_collection.name,
                "localField": "ethAddress",
                "foreignField": "ethAddress",
                "pipeline": address_lookup_pipeline,
                "as": "address_state",
            }
        },
        {"$unwind": "$address_state"},
        {
            "$addFields": {
                "effective_position_value": "$address_state.effective_position_value",
                "account_value": "$address_state.marginSummary.accountValue",
                "withdrawable": "$address_state.withdrawable",
                "state_updated_at": "$address_state.updated_at",
            }
        },
        {"$skip": skip},
        {"$limit": page_size},
        _project_trader_row(),
    ]
    pipeline.append(
        {
            "$facet": {
                "items": item_pipeline,
                "metadata": [{"$count": "total"}],
            }
        }
    )
    return pipeline


def build_trader_pipeline(
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    min_win_rate: Optional[float] = None,
    max_win_rate: Optional[float] = None,
    min_total_trades: Optional[int] = None,
    max_total_trades: Optional[int] = None,
    min_net_pnl: Optional[float] = None,
    max_net_pnl: Optional[float] = None,
    min_position_value: Optional[float] = None,
    max_position_value: Optional[float] = None,
    position_direction: str = "any",
    entry_value_tier: str = "all",
    min_entry_win_rate: Optional[float] = None,
    updated_after: Optional[datetime] = None,
    updated_before: Optional[datetime] = None,
    sort_by: str = "win_rate_score",
    sort_dir: str = "desc",
) -> list[dict[str, Any]]:
    """Build the MongoDB aggregation used by the trader browser."""
    query_filters = {
        "search": search,
        "min_win_rate": min_win_rate,
        "max_win_rate": max_win_rate,
        "min_total_trades": min_total_trades,
        "max_total_trades": max_total_trades,
        "min_net_pnl": min_net_pnl,
        "max_net_pnl": max_net_pnl,
        "min_position_value": min_position_value,
        "max_position_value": max_position_value,
        "position_direction": position_direction,
        "entry_value_tier": entry_value_tier,
        "min_entry_win_rate": min_entry_win_rate,
        "updated_after": updated_after,
        "updated_before": updated_before,
    }
    completed_match = _build_completed_match(query_filters)
    joined_match = _build_joined_match(query_filters)

    sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["win_rate_score"])
    sort_value = 1 if sort_dir == "asc" else -1
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    skip = (page - 1) * page_size

    if sort_by in JOINED_SORT_FIELDS:
        return _build_address_first_trader_pipeline(
            page=page,
            page_size=page_size,
            completed_match=completed_match,
            joined_match=joined_match,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    if joined_match:
        return _build_completed_first_joined_pipeline(
            page=page,
            page_size=page_size,
            completed_match=completed_match,
            joined_match=joined_match,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    pipeline: list[dict[str, Any]] = []
    if completed_match:
        pipeline.append({"$match": completed_match})

    pipeline.extend(
        [
            {"$sort": {sort_field: sort_value, "ethAddress": -sort_value}},
            {
                "$facet": {
                    "items": [
                        {"$skip": skip},
                        {"$limit": page_size},
                        {
                            "$lookup": {
                                "from": web3_hyperliquid_hyper_x_addresses_collection.name,
                                "localField": "ethAddress",
                                "foreignField": "ethAddress",
                                "as": "address_state",
                            }
                        },
                        {
                            "$unwind": {
                                "path": "$address_state",
                                "preserveNullAndEmptyArrays": True,
                            }
                        },
                        {
                            "$addFields": {
                                "effective_position_value": "$address_state.effective_position_value",
                                "account_value": "$address_state.marginSummary.accountValue",
                                "withdrawable": "$address_state.withdrawable",
                                "state_updated_at": "$address_state.updated_at",
                            }
                        },
                        _project_trader_row(),
                    ],
                    "metadata": [{"$count": "total"}],
                }
            },
        ]
    )
    return pipeline


def _project_trader_row() -> dict[str, Any]:
    projection = _trader_projection()
    projection.update(
        {
            "effective_position_value": 1,
            "account_value": 1,
            "withdrawable": 1,
            "state_updated_at": 1,
        }
    )
    return {"$project": projection}


def _trader_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "ethAddress": 1,
        "win_rate": 1,
        "win_rate_score": 1,
        "win_rate_wilson_lower_bound": 1,
        "win_rate_long": 1,
        "win_rate_short": 1,
        "total_trades": 1,
        "winning_trades": 1,
        "completed_trade_pnl": 1,
        "duration_stats": 1,
        "entry_value_summary": 1,
        "processedThroughTime": 1,
        "updated_at": 1,
    }


def _address_state_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "ethAddress": 1,
        "effective_position_value": 1,
        "marginSummary.accountValue": 1,
        "withdrawable": 1,
        "updated_at": 1,
    }


async def _list_traders_by_page_ids(
    *,
    page: int,
    page_size: int,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Page over a covered address index, then fetch only the selected rows."""
    completed_match = _build_completed_match(filters)
    sort_by = filters.get("sort_by", "win_rate_score")
    sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["win_rate_score"])
    sort_value = 1 if filters.get("sort_dir", "desc") == "asc" else -1
    skip = (page - 1) * page_size

    id_cursor = (
        web3_hyperliquid_hyper_x_completed_trades_collection.find(
            completed_match,
            {"_id": 0, "ethAddress": 1},
        )
        .sort([(sort_field, sort_value), ("ethAddress", -sort_value)])
        .skip(skip)
        .limit(page_size)
    )
    has_total_trades_filter = "total_trades" in completed_match
    if has_total_trades_filter and sort_by in {"win_rate", "win_rate_score"}:
        id_cursor = id_cursor.hint(TOTAL_TRADES_RANK_INDEX)

    if not completed_match:
        count_coro = (
            web3_hyperliquid_hyper_x_completed_trades_collection.estimated_document_count()
        )
    else:
        count_options = (
            {"hint": TOTAL_TRADES_RANK_INDEX}
            if has_total_trades_filter
            else {}
        )
        count_coro = (
            web3_hyperliquid_hyper_x_completed_trades_collection.count_documents(
                completed_match,
                **count_options,
            )
        )
    page_refs, total = await asyncio.gather(
        id_cursor.to_list(length=page_size),
        count_coro,
    )
    page_addresses = [row["ethAddress"] for row in page_refs]
    if not page_addresses:
        return [], total

    completed_coro = (
        web3_hyperliquid_hyper_x_completed_trades_collection.find(
            {"ethAddress": {"$in": page_addresses}},
            _trader_projection(),
        ).to_list(length=page_size)
    )
    states_coro = web3_hyperliquid_hyper_x_addresses_collection.find(
        {"ethAddress": {"$in": page_addresses}},
        _address_state_projection(),
    ).to_list(length=page_size)
    completed_rows, address_states = await asyncio.gather(
        completed_coro,
        states_coro,
    )

    completed_by_address = {row["ethAddress"]: row for row in completed_rows}
    state_by_address = {row["ethAddress"]: row for row in address_states}
    items: list[dict[str, Any]] = []
    for address in page_addresses:
        row = completed_by_address.get(address)
        if row is None:
            continue
        state = state_by_address.get(address, {})
        margin_summary = state.get("marginSummary") or {}
        row["effective_position_value"] = state.get("effective_position_value")
        row["account_value"] = margin_summary.get("accountValue")
        row["withdrawable"] = state.get("withdrawable")
        row["state_updated_at"] = state.get("updated_at")
        items.append(row)
    return items, total


async def _list_traders_by_completed_sort_and_state_filter(
    *,
    page: int,
    page_size: int,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Intersect indexed state matches with completed rows, then sort the subset."""
    completed_match = _build_completed_match(filters)
    joined_match = _build_joined_match(filters)
    sort_by = filters.get("sort_by", "win_rate_score")
    sort_field = SORT_FIELDS.get(sort_by, SORT_FIELDS["win_rate_score"])
    sort_value = 1 if filters.get("sort_dir", "desc") == "asc" else -1
    skip = (page - 1) * page_size

    state_refs = await web3_hyperliquid_hyper_x_addresses_collection.find(
        joined_match,
        {"_id": 0, "ethAddress": 1},
    ).to_list(length=None)
    matching_addresses = [row["ethAddress"] for row in state_refs]
    if not matching_addresses:
        return [], 0

    address_match = {"ethAddress": {"$in": matching_addresses}}
    intersection_match = (
        {"$and": [completed_match, address_match]}
        if completed_match
        else address_match
    )
    page_cursor = (
        web3_hyperliquid_hyper_x_completed_trades_collection.find(
            intersection_match,
            _trader_projection(),
        )
        .sort([(sort_field, sort_value), ("ethAddress", -sort_value)])
        .skip(skip)
        .limit(page_size)
    )
    completed_rows, total = await asyncio.gather(
        page_cursor.to_list(length=page_size),
        web3_hyperliquid_hyper_x_completed_trades_collection.count_documents(
            intersection_match
        ),
    )
    page_addresses = [row["ethAddress"] for row in completed_rows]
    state_rows = await web3_hyperliquid_hyper_x_addresses_collection.find(
        {"ethAddress": {"$in": page_addresses}},
        _address_state_projection(),
    ).to_list(length=page_size)
    state_by_address = {row["ethAddress"]: row for row in state_rows}

    items: list[dict[str, Any]] = []
    for row in completed_rows:
        address = row["ethAddress"]
        state = state_by_address.get(address, {})
        margin_summary = state.get("marginSummary") or {}
        row["effective_position_value"] = state.get("effective_position_value")
        row["account_value"] = margin_summary.get("accountValue")
        row["withdrawable"] = state.get("withdrawable")
        row["state_updated_at"] = state.get("updated_at")
        items.append(row)
    return items, total


def serialize_document(value: Any) -> Any:
    """Convert MongoDB/Python values into JSON-friendly structures."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, list):
        return [serialize_document(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_document(item) for key, item in value.items()}
    return value


async def list_traders(**filters: Any) -> dict[str, Any]:
    page = max(int(filters.get("page", 1)), 1)
    page_size = min(max(int(filters.get("page_size", 20)), 1), 200)
    filters = {key: value for key, value in filters.items() if key not in {"page", "page_size"}}

    joined_match = _build_joined_match(filters)
    sort_by = filters.get("sort_by", "win_rate_score")
    if not joined_match and sort_by not in JOINED_SORT_FIELDS:
        items, total = await _list_traders_by_page_ids(
            page=page,
            page_size=page_size,
            filters=filters,
        )
        return {
            "items": serialize_document(items),
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
        }

    if joined_match and sort_by not in JOINED_SORT_FIELDS:
        items, total = await _list_traders_by_completed_sort_and_state_filter(
            page=page,
            page_size=page_size,
            filters=filters,
        )
        return {
            "items": serialize_document(items),
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
        }

    pipeline = build_trader_pipeline(page=page, page_size=page_size, **filters)
    aggregate_collection = (
        web3_hyperliquid_hyper_x_addresses_collection
        if sort_by in JOINED_SORT_FIELDS
        else web3_hyperliquid_hyper_x_completed_trades_collection
    )
    rows = await aggregate_collection.aggregate(
        pipeline
    ).to_list(length=1)
    result = rows[0] if rows else {"items": [], "metadata": []}
    total = result["metadata"][0]["total"] if result["metadata"] else 0
    return {
        "items": serialize_document(result["items"]),
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": ceil(total / page_size) if total else 0,
    }


async def get_dashboard_summary() -> dict[str, Any]:
    """Return the latest precomputed analysis and index-backed leader data."""
    top_cursor = (
        web3_hyperliquid_hyper_x_completed_trades_collection.find(
            {},
            {
                "_id": 0,
                "ethAddress": 1,
                "win_rate": 1,
                "win_rate_score": 1,
                "total_trades": 1,
                "completed_trade_pnl.net": 1,
            },
        )
        .sort([("win_rate_score", -1), ("ethAddress", 1)])
        .limit(6)
    )
    latest_analysis, top_traders, tracked_addresses, trader_count = await asyncio.gather(
        web3_hyperliquid_hyper_x_analyze_result_collection.find_one(
            {},
            {"_id": 0},
            sort=[("timestamp", -1)],
        ),
        top_cursor.to_list(length=6),
        web3_hyperliquid_hyper_x_addresses_collection.estimated_document_count(),
        web3_hyperliquid_hyper_x_completed_trades_collection.estimated_document_count(),
    )

    analysis = latest_analysis or {}
    result = {
        "tracked_addresses": analysis.get("total_addresses", tracked_addresses),
        "trader_count": analysis.get("analyzed_addresses", trader_count),
        "winrate_distribution": analysis.get("winrate_distribution", {}),
        "position_distribution": analysis.get("position_distribution", {}),
        "analysis_updated_at": analysis.get("timestamp"),
        "top_traders": top_traders,
    }
    return serialize_document(result)


async def get_trader_detail(address: str) -> Optional[dict[str, Any]]:
    doc = await web3_hyperliquid_hyper_x_completed_trades_collection.find_one(
        {"ethAddress": address},
        {"_id": 0, "completed_trades": 0},
    )
    if doc is None:
        return None

    state = await web3_hyperliquid_hyper_x_addresses_collection.find_one(
        {"ethAddress": address},
        {"_id": 0},
    )
    doc["address_state"] = state
    return serialize_document(doc)


async def list_trader_trades(
    address: str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> Optional[dict[str, Any]]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    skip = (page - 1) * page_size
    doc = await web3_hyperliquid_hyper_x_completed_trades_collection.find_one(
        {"ethAddress": address},
        {
            "_id": 0,
            "ethAddress": 1,
            "total_trades": 1,
            "completed_trades": {"$slice": [skip, page_size]},
        },
    )
    if doc is None:
        return None

    total = int(doc.get("total_trades") or 0)
    return {
        "items": serialize_document(doc.get("completed_trades", [])),
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": ceil(total / page_size) if total else 0,
    }
