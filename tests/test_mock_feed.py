# tests/test_mock_feed.py
from src.game.mock_feed import MockFeed
from src.game.feed import EventFeed


def test_mock_feed_snapshots_and_status():
    script = {
        "status_by_minute": [(0, "live"), (90, "finished")],
        "snapshots": [
            {"minute": 0, "stats": {"corner_kicks": 0, "goals": 0}},
            {"minute": 5, "stats": {"corner_kicks": 3, "goals": 1}},
        ],
        "lineups": [],
    }
    feed: EventFeed = MockFeed(script)
    assert feed.snapshot_at(5).stats["corner_kicks"] == 3
    assert feed.snapshot_at(0).stats["goals"] == 0
    assert feed.match_status_at(0) == "live"
    assert feed.match_status_at(90) == "finished"
