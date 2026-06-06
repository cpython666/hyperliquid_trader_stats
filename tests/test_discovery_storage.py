import json

from hyperliquid_trader_stats.discovery import extract_user_addresses, is_eth_address
from hyperliquid_trader_stats.mongo_store import _completed_trade_payload
from hyperliquid_trader_stats.storage import FileStore


def test_extract_user_addresses_from_block_details():
    block = {
        "blockDetails": {
            "txs": [
                {"user": "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD"},
                {"user": "Leader"},
                {"user": "0x1111111111111111111111111111111111111111"},
                {"user": None},
            ]
        }
    }

    addresses, tx_count, invalid_count = extract_user_addresses(block)

    assert tx_count == 4
    assert invalid_count == 1
    assert addresses == [
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        "0x1111111111111111111111111111111111111111",
    ]
    assert is_eth_address(addresses[0])


def test_file_store_upserts_address_book(tmp_path):
    store = FileStore(tmp_path)

    first = store.upsert_addresses(
        [
            "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD",
            "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD",
        ],
        source="block_scan",
        metadata_by_address={
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd": {"last_block_height": 100}
        },
    )
    second = store.upsert_addresses(
        ["0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"],
        source="leaderboard",
        metadata_by_address={
            "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd": {"last_block_height": 90}
        },
    )

    records = json.loads(store.address_book_path.read_text(encoding="utf-8"))

    assert first == {"new": 1, "updated": 0, "total": 1}
    assert second == {"new": 0, "updated": 1, "total": 1}
    assert records[0]["ethAddress"] == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert records[0]["seen_count"] == 3
    assert records[0]["sources"] == ["block_scan", "leaderboard"]
    assert records[0]["last_block_height"] == 100
    assert store.load_address_book_addresses() == ["0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"]
    assert store.address_book_csv_path.exists()
    assert store.address_book_txt_path.exists()


def test_completed_trade_payload_keeps_legacy_mongo_fields():
    result = {
        "summary": {
            "address": "0xabc",
            "total_trades": 1,
            "winning_trades": 1,
            "win_rate": 100.0,
            "win_rate_score": 69.31,
            "win_rate_wilson_lower_bound": 20.65,
            "win_rate_long": 100.0,
            "win_rate_short": 0.0,
            "gross_pnl": 20.0,
            "fees": 2.0,
            "net_pnl": 18.0,
            "avg_duration_minutes": 1.0,
            "median_duration_minutes": 1.0,
        },
        "trades": [
            {
                "coin": "BTC",
                "direction": "Long",
                "closed_pnl": 20.0,
                "fees": 2.0,
                "net_pnl": 18.0,
                "entry_value": 10000.0,
            }
        ],
        "per_asset": {
            "BTC": {
                "total_pnl": 20.0,
                "fees": 2.0,
                "net_pnl": 18.0,
                "trades": 1,
            }
        },
    }

    payload = _completed_trade_payload("0xabc", result)

    assert payload["ethAddress"] == "0xabc"
    assert payload["completed_trades"] == result["trades"]
    assert payload["completed_trade_pnl"]["net"] == 18.0
    assert payload["stats_per_asset"]["BTC"]["number_of_trades"] == 1
    assert payload["total_trades"] == 1
    assert payload["win_rate"] == 100.0
    assert "analysis_result_v2" in payload
