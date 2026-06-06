from hyperliquid_trader_stats.analysis import TraderInput, analyze_population, analyze_trader, merge_fills_to_completed_trades


def fill(tid, coin, time, start_position, direction, price, size, pnl, fee):
    return {
        "tid": tid,
        "coin": coin,
        "time": time,
        "startPosition": str(start_position),
        "dir": direction,
        "px": str(price),
        "sz": str(size),
        "closedPnl": str(pnl),
        "fee": str(fee),
    }


def test_merge_fills_to_completed_trades_groups_by_coin_and_start_position():
    fills = [
        fill(1, "BTC", 1000, 0, "Open Long", 100, 1, 0, 1),
        fill(2, "BTC", 2000, 1, "Close Long", 120, 1, 20, 1),
        fill(3, "ETH", 3000, 0, "Open Short", 50, 2, 0, 1),
        fill(4, "ETH", 4000, -2, "Close Short", 40, 2, 20, 1),
    ]

    trades = merge_fills_to_completed_trades(fills)

    assert len(trades) == 2
    assert trades[0]["coin"] == "BTC"
    assert trades[0]["net_pnl"] == 18
    assert trades[0]["direction"] == "Long"
    assert trades[1]["coin"] == "ETH"
    assert trades[1]["net_pnl"] == 18
    assert trades[1]["direction"] == "Short"


def test_open_position_coin_removes_latest_completed_trade_for_that_coin():
    fills = [
        fill(1, "BTC", 1000, 0, "Open Long", 100, 1, 0, 1),
        fill(2, "BTC", 2000, 1, "Close Long", 120, 1, 20, 1),
        fill(3, "BTC", 3000, 0, "Open Long", 130, 1, 0, 1),
        fill(4, "BTC", 4000, 1, "Close Long", 140, 1, 10, 1),
    ]

    trades = merge_fills_to_completed_trades(fills, open_position_coins=["BTC"])

    assert len(trades) == 1
    assert trades[0]["end_time_ms"] == 2000


def test_analyze_trader_and_population():
    trader = TraderInput(
        address="0xabc",
        fills=[
            fill(1, "BTC", 1000, 0, "Open Long", 100, 1, 0, 1),
            fill(2, "BTC", 2000, 1, "Close Long", 120, 1, 20, 1),
            fill(3, "ETH", 3000, 0, "Open Short", 50, 2, 0, 1),
            fill(4, "ETH", 4000, -2, "Close Short", 60, 2, -20, 1),
        ],
        open_position_coins=[],
        effective_position_value=1000,
    )

    result = analyze_trader(trader)
    population = analyze_population([result])

    assert result["summary"]["total_trades"] == 2
    assert result["summary"]["winning_trades"] == 1
    assert result["summary"]["win_rate"] == 50
    assert result["summary"]["net_pnl"] == -4
    assert population["winrate_distribution"]["ge_50"] == 1
    assert population["position_distribution"]["ge_50"]["long"] == 1

