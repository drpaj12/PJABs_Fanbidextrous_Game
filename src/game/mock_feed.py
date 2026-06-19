# src/game/mock_feed.py
"""A canned replay feed implementing EventFeed, for offline play and tests."""
from src.game.sport_event import SportEvent, WindowSnapshot


class MockFeed:
    def __init__(self, script: dict) -> None:
        self._snapshots = {s["minute"]: WindowSnapshot(minute=s["minute"], stats=dict(s["stats"]))
                           for s in script.get("snapshots", [])}
        self._status = sorted((int(m), s) for m, s in script.get("status_by_minute", [(0, "live")]))
        self._lineups = script.get("lineups", [])

    def snapshot_at(self, minute: int) -> WindowSnapshot:
        if minute in self._snapshots:
            return self._snapshots[minute]
        # nearest earlier snapshot, else empty
        earlier = [m for m in self._snapshots if m <= minute]
        if earlier:
            return self._snapshots[max(earlier)]
        return WindowSnapshot(minute=minute, stats={})

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    def match_status_at(self, minute: int) -> str:
        status = "live"
        for m, s in self._status:
            if m <= minute:
                status = s
        return status

    def match_status(self) -> str:
        return self._status[-1][1] if self._status else "live"

    def last_known_minute(self) -> int:
        """Largest minute the feed has data for -- the bound for an open poll loop."""
        minutes = list(self._snapshots) + [m for m, _ in self._status]
        return max(minutes) if minutes else 0

    def lineups(self) -> list[dict]:
        return list(self._lineups)
