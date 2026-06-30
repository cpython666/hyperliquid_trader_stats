from datetime import datetime

import pytest

from hyperliquid_trader_stats.services.fetch_and_store_user_state import (
    _build_user_state_query,
)


def test_incremental_query_selects_addresses_without_state():
    assert _build_user_state_query() == {
        "ethAddress": {"$regex": "^0x"},
        "marginSummary": {"$exists": False},
    }


def test_full_query_selects_all_valid_addresses():
    assert _build_user_state_query(incremental=False) == {
        "ethAddress": {"$regex": "^0x"},
    }


def test_updated_before_query_selects_stale_and_never_updated_addresses():
    cutoff = datetime(2026, 6, 1)

    assert _build_user_state_query(updated_before=cutoff) == {
        "ethAddress": {"$regex": "^0x"},
        "$or": [
            {"updated_at": {"$lte": cutoff}},
            {"updated_at": {"$exists": False}},
        ],
    }


def test_full_query_rejects_updated_before_filter():
    with pytest.raises(ValueError, match="全量模式不能与更新时间筛选同时使用"):
        _build_user_state_query(
            incremental=False,
            updated_before=datetime(2026, 6, 1),
        )
