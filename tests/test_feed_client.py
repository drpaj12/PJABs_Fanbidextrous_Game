import asyncio
import json
from src.sync.feed_client import FeedClient


class _FakeTransport:
    def __init__(self):
        self.gets: list[str] = []

    async def get(self, url: str) -> str:
        self.gets.append(url)
        return json.dumps({"lineups": None, "statistics": None,
                           "fixture": None, "cached_at": 0})

    async def post(self, url: str, body: str) -> str:  # unused by FeedClient
        return "{}"


def test_lead_client_requests_upstream_fetch():
    t = _FakeTransport()
    client = FeedClient(base_url="http://x", transport=t, is_lead=True)
    asyncio.run(client.get_feed(1539007))
    assert "fixture=1539007" in t.gets[0]
    assert "lead=1" in t.gets[0]


def test_follower_never_asks_to_spend_quota():
    t = _FakeTransport()
    client = FeedClient(base_url="http://x", transport=t)  # is_lead defaults False
    asyncio.run(client.get_feed(1539007))
    assert "fixture=1539007" in t.gets[0]
    assert "lead=1" not in t.gets[0]


def test_get_feed_parses_snapshot_json():
    t = _FakeTransport()
    client = FeedClient(base_url="http://x", transport=t)
    snap = asyncio.run(client.get_feed(42))
    assert snap["cached_at"] == 0 and "lineups" in snap
