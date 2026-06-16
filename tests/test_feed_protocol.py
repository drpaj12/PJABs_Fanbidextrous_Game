# tests/test_feed_protocol.py
from src.game.feed import EventFeed
from src.game.sport_event import WindowSnapshot, SportEvent


class _Stub:
    def snapshot_at(self, minute: int) -> WindowSnapshot:
        return WindowSnapshot(minute=minute, stats={"goals": 0})

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    def match_status(self) -> str:
        return "live"


def test_stub_satisfies_protocol():
    feed: EventFeed = _Stub()
    assert feed.snapshot_at(5).minute == 5
    assert feed.events_between(0, 5) == []
    assert feed.match_status() == "live"
