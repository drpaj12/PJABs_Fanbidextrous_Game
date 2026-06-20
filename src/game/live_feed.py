# src/game/live_feed.py
"""Live match feed: adapts API-Football v3 relay snapshots into the EventFeed interface.

A "relay snapshot" is the feed_cache.php shape:
    {"lineups": <fixtures/lineups>, "statistics": <fixtures/statistics>,
     "fixture": <fixtures?id=>, "cached_at": <epoch>}

Pure: no pygame, no network. Fetching lives in src/sync/feed_client.FeedClient; this class
only transforms already-fetched JSON and accumulates one cumulative WindowSnapshot per
observed minute -- the same schema MockFeed/ReplayFeed expose. The live sibling of
ReplayFeed: where ReplayFeed reads a recorded file, LiveFeed is fed snapshots over time.
"""
from typing import Optional
from src.game.sport_event import SportEvent, WindowSnapshot
from src.game.normalize_soccer import parse_lineups, parse_statistics, map_status


class LiveFeed:
    def __init__(self, snapshot: Optional[dict] = None) -> None:
        self._snapshots: dict[int, WindowSnapshot] = {}
        self._lineups_raw: dict = {"response": []}
        self._status_short: str = "NS"
        self._elapsed: int = 0
        self._home_team: str = ""
        self._away_team: str = ""
        self._kickoff_iso: Optional[str] = None
        if snapshot is not None:
            self.record(snapshot)

    # -- ingest -------------------------------------------------------------
    def record(self, snapshot: dict, minute: Optional[int] = None) -> None:
        """Ingest one relay snapshot, recording a cumulative WindowSnapshot at the match's
        current elapsed minute (or `minute` if given). Empty lineups are ignored so a
        pre-match poll does not wipe a previously seen lineup."""
        fixture = self._first(snapshot.get("fixture"))
        fixture_block = fixture.get("fixture", {})
        status = fixture_block.get("status", {})
        if status.get("short"):
            self._status_short = status["short"]
        if fixture_block.get("date"):
            self._kickoff_iso = fixture_block["date"]
        if status.get("elapsed") is not None:
            self._elapsed = int(status["elapsed"])
        teams = fixture.get("teams") or {}
        home_name = (teams.get("home") or {}).get("name")
        away_name = (teams.get("away") or {}).get("name")
        if home_name:
            self._home_team = home_name
        if away_name:
            self._away_team = away_name
        lineups = snapshot.get("lineups") or {}
        if lineups.get("response"):
            self._lineups_raw = lineups
        m = minute if minute is not None else self._elapsed
        stats = parse_statistics(snapshot.get("statistics") or {})
        stats["goals"] = self._goals(fixture)
        self._snapshots[m] = WindowSnapshot(minute=m, stats=stats)

    @staticmethod
    def _first(block: Optional[dict]) -> dict:
        resp = (block or {}).get("response") or []
        return resp[0] if resp else {}

    @staticmethod
    def _goals(fixture: dict) -> int:
        g = fixture.get("goals") or {}
        return int(g.get("home") or 0) + int(g.get("away") or 0)

    # -- EventFeed interface ------------------------------------------------
    def lineups(self) -> list[dict]:
        """Starter rows only (the 22-player draft pool), as MockFeed-style dicts."""
        athletes = parse_lineups(self._lineups_raw, groups=("startXI",))
        return [{"athlete_id": a.athlete_id, "name": a.name,
                 "broad_position": a.broad_position, "team": a.team,
                 "jersey": a.jersey} for a in athletes]

    def snapshot_at(self, minute: int) -> WindowSnapshot:
        if minute in self._snapshots:
            return self._snapshots[minute]
        earlier = [m for m in self._snapshots if m <= minute]
        if earlier:
            return self._snapshots[max(earlier)]
        return WindowSnapshot(minute=minute, stats={})

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    def match_status_at(self, minute: int) -> str:
        return map_status(self._status_short)

    def match_status(self) -> str:
        return map_status(self._status_short)

    def last_known_minute(self) -> int:
        return max(self._snapshots) if self._snapshots else self._elapsed

    # -- live extras --------------------------------------------------------
    def current_minute(self) -> int:
        """The match's live elapsed minute as last reported by the API."""
        return self._elapsed

    def has_lineups(self) -> bool:
        """True once the API has published a starting XI (drafting can begin)."""
        return bool(self._lineups_raw.get("response"))

    def home_team(self) -> str:
        """Home team name from the fixture payload (empty until first poll)."""
        return self._home_team

    def away_team(self) -> str:
        """Away team name from the fixture payload (empty until first poll)."""
        return self._away_team

    def kickoff_iso(self) -> Optional[str]:
        """Scheduled kickoff timestamp (ISO 8601) from the fixture payload, or None until
        a poll has returned one. Drives the pre-game countdown."""
        return self._kickoff_iso

    def seed_kickoff(self, kickoff_iso: str) -> None:
        """Set the scheduled kickoff from a non-API source (config) so the countdown shows
        with zero API calls. A real poll's fixture.date overrides this (see record())."""
        if kickoff_iso:
            self._kickoff_iso = kickoff_iso

    def status_short(self) -> str:
        """Raw API-Football status code (NS, 1H, HT, FT, ...) before engine mapping."""
        return self._status_short
