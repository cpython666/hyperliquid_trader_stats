import asyncio

from hyperliquid_trader_stats.web import queries
from hyperliquid_trader_stats.web.queries import build_trader_pipeline


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sort_spec = None
        self.skip_value = 0
        self.limit_value = None
        self.hint_value = None

    def sort(self, sort_spec):
        self.sort_spec = sort_spec
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def hint(self, value):
        self.hint_value = value
        return self

    async def to_list(self, length):
        end = self.skip_value + (self.limit_value or length)
        return self.rows[self.skip_value:end]


class _FakeTradeSummaryCollection:
    def __init__(self):
        self.aggregate_called = False
        self.count_hint = None
        self.id_cursor = None

    def find(self, match, projection):
        if projection == {"_id": 0, "ethAddress": 1}:
            self.id_cursor = _FakeCursor(
                [{"ethAddress": "0x2"}, {"ethAddress": "0x1"}]
            )
            return self.id_cursor
        return _FakeCursor(
            [
                {"ethAddress": "0x1", "win_rate": 80},
                {"ethAddress": "0x2", "win_rate": 90},
            ]
        )

    async def estimated_document_count(self):
        return 2

    async def count_documents(self, match, **options):
        self.count_hint = options.get("hint")
        return 2

    def aggregate(self, pipeline):
        self.aggregate_called = True
        raise AssertionError("普通排序不应进入全量聚合管线")


class _FakeAddressCollection:
    name = "addresses"

    def find(self, match, projection):
        return _FakeCursor(
            [
                {
                    "ethAddress": "0x1",
                    "effective_position_value": 10,
                    "marginSummary": {"accountValue": 20},
                },
                {
                    "ethAddress": "0x2",
                    "effective_position_value": 30,
                    "marginSummary": {"accountValue": 40},
                },
            ]
        )


class _FakeDetailCollection:
    def __init__(self, result):
        self.result = result
        self.last_match = None
        self.last_projection = None

    async def find_one(self, match, projection):
        self.last_match = match
        self.last_projection = projection
        return self.result


class _FakeTradeRowsCollection:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total
        self.last_match = None
        self.last_projection = None
        self.last_count_match = None

    def find(self, match, projection):
        self.last_match = match
        self.last_projection = projection
        return _FakeCursor(self.rows)

    async def count_documents(self, match):
        self.last_count_match = match
        return self.total


def test_build_trader_pipeline_applies_completed_and_joined_filters():
    pipeline = build_trader_pipeline(
        search="0xabc",
        min_win_rate=60,
        min_total_trades=20,
        min_position_value=1000,
        position_direction="long",
        entry_value_tier="10w",
        min_entry_win_rate=70,
        sort_by="position_value",
        sort_dir="asc",
    )

    assert pipeline[0] == {
        "$match": {"effective_position_value": {"$gt": 1000}}
    }
    assert pipeline[1] == {
        "$sort": {"effective_position_value": 1, "ethAddress": -1}
    }
    item_pipeline = pipeline[-1]["$facet"]["items"]
    lookup = next(stage["$lookup"] for stage in item_pipeline if "$lookup" in stage)
    assert lookup["localField"] == "ethAddress"
    assert lookup["pipeline"][0] == {
        "$match": {
            "ethAddress": {"$regex": "0xabc", "$options": "i"},
            "win_rate": {"$gte": 60},
            "total_trades": {"$gte": 20},
            "entry_value_summary.win_rate_over_10w.win_rate": {"$gte": 70},
        }
    }
    assert "completed_trades" not in lookup["pipeline"][-1]["$project"]


def test_full_address_search_uses_exact_index_lookup():
    address = "0x" + ("a" * 40)

    pipeline = build_trader_pipeline(search=address)

    assert pipeline[0] == {"$match": {"ethAddress": address}}


def test_joined_filter_preserves_completed_sort_index():
    pipeline = build_trader_pipeline(
        min_position_value=1000,
        sort_by="win_rate_score",
        sort_dir="desc",
    )

    assert pipeline[0] == {
        "$sort": {"win_rate_score": -1, "ethAddress": 1}
    }
    assert pipeline[1] == {"$project": queries._trader_projection()}
    item_pipeline = pipeline[-1]["$facet"]["items"]
    lookup = next(stage["$lookup"] for stage in item_pipeline if "$lookup" in stage)
    assert (
        lookup["from"]
        == queries.web3_hyperliquid_hyper_x_addresses_collection.name
    )
    assert lookup["pipeline"][0] == {
        "$match": {"effective_position_value": {"$gte": 1000}}
    }


def test_build_trader_pipeline_looks_up_only_paged_rows_by_default():
    pipeline = build_trader_pipeline()
    facet = pipeline[-1]["$facet"]["items"]

    assert pipeline[0] == {"$sort": {"win_rate_score": -1, "ethAddress": 1}}
    assert facet[0] == {"$skip": 0}
    assert facet[1] == {"$limit": 20}
    assert "$lookup" in facet[2]


def test_build_trader_pipeline_paginates_and_caps_page_size():
    pipeline = build_trader_pipeline(page=3, page_size=500)
    facet = pipeline[-1]["$facet"]["items"]

    assert {"$skip": 400} in facet
    assert {"$limit": 200} in facet


def test_list_traders_pages_by_address_before_fetching_rows(monkeypatch):
    summary = _FakeTradeSummaryCollection()
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        summary,
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_addresses_collection",
        _FakeAddressCollection(),
    )

    result = asyncio.run(
        queries.list_traders(
            page=1,
            page_size=50,
            sort_by="win_rate",
            sort_dir="desc",
        )
    )

    assert summary.aggregate_called is False
    assert summary.id_cursor.sort_spec == [
        ("win_rate", -1),
        ("ethAddress", 1),
    ]
    assert [item["ethAddress"] for item in result["items"]] == ["0x2", "0x1"]
    assert result["items"][0]["account_value"] == 40
    assert result["total"] == 2


def test_total_trades_filter_uses_covered_rank_index(monkeypatch):
    summary = _FakeTradeSummaryCollection()
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        summary,
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_addresses_collection",
        _FakeAddressCollection(),
    )

    asyncio.run(
        queries.list_traders(
            page=1,
            page_size=50,
            min_total_trades=20,
            sort_by="win_rate_score",
            sort_dir="desc",
        )
    )

    assert summary.id_cursor.hint_value == queries.TOTAL_TRADES_RANK_INDEX
    assert summary.count_hint == queries.TOTAL_TRADES_RANK_INDEX


def test_trader_detail_uses_trade_summary(monkeypatch):
    summary = _FakeDetailCollection(
        {
            "ethAddress": "0x1",
            "total_trades": 120,
            "win_rate": 75,
        }
    )
    address_state = _FakeDetailCollection(
        {"ethAddress": "0x1", "withdrawable": "10"}
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        summary,
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_addresses_collection",
        address_state,
    )

    result = asyncio.run(queries.get_trader_detail("0x1"))

    assert summary.last_projection == {"_id": 0}
    assert result["address_state"]["withdrawable"] == "10"


def test_trader_trades_are_loaded_from_completed_trade_rows(monkeypatch):
    summary = _FakeDetailCollection({"ethAddress": "0x1", "total_trades": 120})
    trades = _FakeTradeRowsCollection(
        [{"coin": "BTC"}, {"coin": "ETH"}],
        total=120,
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        summary,
    )
    monkeypatch.setattr(
        queries,
        "web3_hyperliquid_hyper_x_completed_trades_collection",
        trades,
    )

    result = asyncio.run(
        queries.list_trader_trades("0x1", page=1, page_size=50)
    )

    assert trades.last_match == {"ethAddress": "0x1"}
    assert trades.last_projection == {"_id": 0}
    assert trades.last_count_match == {"ethAddress": "0x1"}
    assert result == {
        "items": [{"coin": "BTC"}, {"coin": "ETH"}],
        "page": 1,
        "page_size": 50,
        "total": 120,
        "pages": 3,
    }
