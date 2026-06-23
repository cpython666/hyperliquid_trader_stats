import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from hyperliquid_trader_stats.analytics import compute_complete_trades


class FakeResponse:
    def __init__(self, status, *, payload=None, headers=None, text=""):
        self.status = status
        self.payload = payload
        self.headers = headers or {}
        self.response_text = text

    async def json(self):
        return self.payload

    async def text(self):
        return self.response_text


class FakeRequestContext:
    def __init__(self, outcome):
        self.outcome = outcome

    async def __aenter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.post_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    def post(self, *_args, **_kwargs):
        self.post_count += 1
        return FakeRequestContext(self.outcomes.pop(0))


class GetUserOpenPositionCoinsTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_timeout_then_returns_positions(self):
        session = FakeSession(
            [
                asyncio.TimeoutError(),
                FakeResponse(
                    200,
                    payload={
                        "assetPositions": [
                            {"position": {"coin": "BTC"}},
                            {"position": {"coin": "ETH"}},
                        ]
                    },
                ),
            ]
        )
        sleep = AsyncMock()

        with (
            patch.object(
                compute_complete_trades.aiohttp,
                "ClientSession",
                return_value=session,
            ),
            patch.object(compute_complete_trades.asyncio, "sleep", sleep),
        ):
            result = await compute_complete_trades.get_user_open_position_coins(
                "0xtest",
                retries=3,
                timeout=1,
                retry_delay=2,
            )

        self.assertEqual(result, ["BTC", "ETH"])
        self.assertEqual(session.post_count, 2)
        sleep.assert_awaited_once_with(2)

    async def test_raises_after_all_retries_timeout(self):
        session = FakeSession([asyncio.TimeoutError() for _ in range(3)])
        sleep = AsyncMock()

        with (
            patch.object(
                compute_complete_trades.aiohttp,
                "ClientSession",
                return_value=session,
            ),
            patch.object(compute_complete_trades.asyncio, "sleep", sleep),
        ):
            with self.assertRaisesRegex(RuntimeError, "已重试 3 次"):
                await compute_complete_trades.get_user_open_position_coins(
                    "0xtest",
                    retries=3,
                    timeout=1,
                    retry_delay=2,
                )

        self.assertEqual(session.post_count, 3)
        self.assertEqual([item.args[0] for item in sleep.await_args_list], [2, 4])


if __name__ == "__main__":
    unittest.main()
