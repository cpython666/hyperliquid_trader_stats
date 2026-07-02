import asyncio

from hyperliquid_trader_stats.plotting import analyze_ls_rate_over_value_pro as analysis


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def batch_size(self, _size):
        return self

    def __aiter__(self):
        self._iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    async def estimated_document_count(self):
        return len(self.rows)

    def find(self, _query, _projection):
        return _FakeCursor(self.rows)


def _position(coin, size, value):
    return {
        "position": {
            "coin": coin,
            "szi": str(size),
            "positionValue": str(value),
        }
    }


def test_extract_coin_positions_uses_size_for_direction_and_value_magnitude():
    result = analysis._extract_coin_position_values(
        {
            "assetPositions": [
                _position("BTC", 1, -100),
                _position("ETH", -2, 50),
                _position("ZERO", 0, 10),
                {"position": {"coin": "BAD", "szi": "x", "positionValue": "1"}},
            ]
        }
    )

    assert result == {"BTC": 100.0, "ETH": -50.0}


def test_analysis_adds_only_aggregated_coin_snapshot(monkeypatch):
    addresses = _FakeCollection(
        [
            {
                "ethAddress": "0x1",
                "effective_position_value": 50,
                "state": {
                    "assetPositions": [
                        _position("BTC", 1, 100),
                        _position("ETH", -1, 50),
                    ]
                },
            },
            {
                "ethAddress": "0x2",
                "effective_position_value": -20,
                "state": {
                    "assetPositions": [
                        _position("BTC", -1, 40),
                        _position("SOL", 1, 20),
                    ]
                },
            },
        ]
    )
    trades = _FakeCollection(
        [
            {"ethAddress": "0x1", "win_rate": 80},
            {"ethAddress": "0x2", "win_rate": 60},
        ]
    )
    monkeypatch.setattr(
        analysis, "web3_hyperliquid_hyper_x_addresses_collection", addresses
    )
    monkeypatch.setattr(
        analysis,
        "web3_hyperliquid_hyper_x_trade_summary_collection",
        trades,
    )

    result = asyncio.run(analysis.analyze_winrate_and_positions())
    coin_snapshot = result["coin_position_distribution"]

    assert list(coin_snapshot) == ["BTC", "ETH", "SOL"]
    assert coin_snapshot["BTC"]["ge_60"] == {
        "long": 1,
        "short": 1,
        "long_value_sum": 100.0,
        "short_value_sum": -40.0,
        "ratio": 1.0,
        "value_ratio": 2.5,
    }
    assert coin_snapshot["BTC"]["ge_70"]["long"] == 1
    assert coin_snapshot["BTC"]["ge_70"]["short"] == 0
    assert coin_snapshot["SOL"]["ge_70"]["long"] == 0
    assert "coin_positions_by_address" not in result
