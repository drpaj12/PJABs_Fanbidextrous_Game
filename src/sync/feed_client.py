"""Fetch the cached feed snapshot from the PHP relay (server-side proxy of API-Football).

The relay caches per fixture so every client shares one upstream quota draw. Only the
lead client (is_lead=True) is allowed to trigger upstream fetches; followers always read
whatever the relay has cached. The client just asks for a fixture id.
"""
import json
from typing import Any
from src.sync.relay_client import Transport, UrllibTransport


class FeedClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 feed_path: str = "/feed_cache.php", is_lead: bool = False) -> None:
        self._base = base_url.rstrip("/")
        self._path = feed_path
        self._t = transport or UrllibTransport()
        self._is_lead = is_lead

    async def get_feed(self, fixture_id: int) -> dict[str, Any]:
        url = f"{self._base}{self._path}?fixture={fixture_id}"
        if self._is_lead:
            url += "&lead=1"
        return json.loads(await self._t.get(url))
