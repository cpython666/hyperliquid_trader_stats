import asyncio

from hyperliquid_trader_stats.hyper_x_utils import fetch_user_fills


class FakeResponse:
    """模拟 aiohttp 响应对象，支持 async with 和 json 读取。"""

    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class FakePostContext:
    """模拟 session.post 返回的异步上下文管理器。"""

    def __init__(self, item):
        self.item = item

    async def __aenter__(self):
        if isinstance(self.item, BaseException):
            raise self.item
        return self.item

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    """按顺序返回预设响应或异常的 session。"""

    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return FakePostContext(self.items.pop(0))


def fill(tid, time):
    """构造最小 fills 数据。"""
    return {"tid": tid, "time": time}


def test_fetch_user_fills_returns_empty_list_without_retry_when_no_new_data():
    """接口首次返回空 fills 时应直接判定无新数据，不再重试。"""
    session = FakeSession([FakeResponse({"fills": []})])

    result = asyncio.run(fetch_user_fills(session, "0xabc", retries=3))

    assert result == []
    assert session.calls == 1


def test_fetch_user_fills_returns_none_when_first_page_times_out():
    """首个分页连续超时时没有可存储数据，应返回 None 表示请求失败。"""
    session = FakeSession([
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
    ])

    result = asyncio.run(fetch_user_fills(session, "0xabc", retries=3, timeout=1))

    assert result is None
    assert session.calls == 3


def test_fetch_user_fills_returns_partial_records_when_later_page_times_out():
    """后续分页超时时应返回前面已获取到的数据，让调用方可以先入库。"""
    first_page = [fill(i, 1000 + i) for i in range(2000)]
    session = FakeSession([
        FakeResponse({"fills": first_page}),
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
    ])

    result = asyncio.run(fetch_user_fills(session, "0xabc", retries=3, timeout=1))

    assert result == first_page
    assert session.calls == 4
