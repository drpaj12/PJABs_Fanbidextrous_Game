# src/sync/sim_feed_client.py
"""Drop-in replacement for FeedClient used by the realtime SIM harness. Same surface the
flow calls (get_feed / get_live_fixtures / is_lead / transport_name), but it makes NO
network call: it is the single point that, in the live path, would hit the API. Each call
writes a [drpaj] QUERY line to the DiagLog so the developer sees exactly WHAT query would
have fired and WHEN, then returns an empty relay snapshot (SimLiveFeed ignores record()).
"""
from typing import Any


class SimFeedClient:
    def __init__(self, diag, sim_feed, fixture_label: str, is_lead: bool = True) -> None:
        self._diag = diag
        self._feed = sim_feed
        self._label = fixture_label
        self._is_lead = is_lead
        self.queries = 0

    @property
    def is_lead(self) -> bool:
        return self._is_lead

    @property
    def transport_name(self) -> str:
        return "SimFeedClient"

    async def get_feed(self, fixture_id: int) -> dict[str, Any]:
        self.queries += 1
        lkm = self._feed.last_known_minute()
        status = self._feed.match_status()
        self._diag.add(self._feed.current_minute(), "QUERY",
                       f"get_feed(fixture={self._label}) -> lkm={lkm}' status={status}")
        # Empty relay snapshot: progress comes from the virtual clock, not this payload.
        return {}

    async def get_live_fixtures(self) -> dict[str, Any]:
        return {"response": []}
