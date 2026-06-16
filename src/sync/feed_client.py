"""Fetch the cached feed snapshot from the PHP relay (server-side proxy of API-Football).

The relay caches per fixture so both clients share one upstream quota draw; the client just
asks for a fixture id.
"""
import json
from typing import Any
from src.sync.relay_client import Transport, UrllibTransport


class FeedClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 feed_path: str = "/feed_cache.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = feed_path
        self._t = transport or UrllibTransport()

    async def get_feed(self, fixture_id: int) -> dict[str, Any]:
        url = f"{self._base}{self._path}?fixture={fixture_id}"
        return json.loads(await self._t.get(url))
