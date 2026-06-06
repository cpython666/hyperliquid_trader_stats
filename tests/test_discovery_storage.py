import json

from hyperliquid_trader_stats.discovery import extract_top_trader_addresses, extract_user_addresses, is_eth_address
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
    store.upsert_addresses(
        ["0x1111111111111111111111111111111111111111"],
        source="hyperdash_top_traders",
        metadata_by_address={
            "0x1111111111111111111111111111111111111111": {"hyperdash_account_value": 1000}
        },
    )

    records = json.loads(store.address_book_path.read_text(encoding="utf-8"))

    assert first == {"new": 1, "updated": 0, "total": 1}
    assert second == {"new": 0, "updated": 1, "total": 1}
    first_record = next(record for record in records if record["ethAddress"] == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd")
    assert first_record["seen_count"] == 3
    assert first_record["sources"] == ["block_scan", "leaderboard"]
    assert first_record["last_block_height"] == 100
    assert store.load_address_book_addresses()[0] == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert store.load_address_book_addresses(sort_by="hyperdash_account_value")[0] == "0x1111111111111111111111111111111111111111"
    assert store.address_book_csv_path.exists()
    assert store.address_book_txt_path.exists()


def test_extract_top_trader_addresses_keeps_hyperdash_metadata():
    data = [
        {
            "address": "0x8af700ba841f30e0a3fcb0ee4c4a9d223e1efa05",
            "account_value": 16518421.685356,
            "main_position": {"coin": "BTC", "value": 75791933.5, "side": "LONG"},
            "direction_bias": 70.66,
            "perp_day_pnl": 273877.442091,
            "perp_week_pnl": 371784.312962,
            "perp_month_pnl": 4678509.584475,
            "perp_alltime_pnl": 45436393.265356,
        },
        {"address": "Leader"},
    ]

    addresses, metadata_by_address, invalid_count = extract_top_trader_addresses(data)

    assert addresses == ["0x8af700ba841f30e0a3fcb0ee4c4a9d223e1efa05"]
    assert invalid_count == 1
    metadata = metadata_by_address[addresses[0]]
    assert metadata["hyperdash_account_value"] == 16518421.685356
    assert metadata["hyperdash_main_position"]["coin"] == "BTC"
    assert metadata["hyperdash_perp_alltime_pnl"] == 45436393.265356


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
