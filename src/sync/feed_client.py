"""Fetch the cached feed snapshot from the PHP relay (server-side proxy of API-Football).

The relay caches per fixture so every client shares one upstream quota draw. Only the
lead client (is_lead=True) is allowed to trigger upstream fetches; followers always read
whatever the relay has cached. The client just asks for a fixture id.
"""
import json
from typing import Any
from src.sync.relay_client import Transport, default_transport


class FeedClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 feed_path: str = "/feed_cache.php", is_lead: bool = False,
                 live_fixtures_path: str = "/live_fixtures.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = feed_path
        self._live_path = live_fixtures_path
        self._t = transport or default_transport()
        self._is_lead = is_lead

    @property
    def is_lead(self) -> bool:
        """True if this client triggers upstream fetches (the others read the cache)."""
        return self._is_lead

    @property
    def transport_name(self) -> str:
        """Class name of the active transport (FetchTransport in WASM, UrllibTransport on
        desktop). Surfaced on screen for diagnosing which network path a client took."""
        return type(self._t).__name__

    async def get_feed(self, fixture_id: int) -> dict[str, Any]:
        url = f"{self._base}{self._path}?fixture={fixture_id}"
        if self._is_lead:
            url += "&lead=1"
        return json.loads(await self._t.get(url))

    async def get_live_fixtures(self) -> dict[str, Any]:
        """Fetch the currently-live World Cup fixtures (filtered server-side) so the client
        can match a picked game to its real fixture id. Lead-gated like get_feed."""
        url = f"{self._base}{self._live_path}"
        if self._is_lead:
            url += "?lead=1"
        return json.loads(await self._t.get(url))
