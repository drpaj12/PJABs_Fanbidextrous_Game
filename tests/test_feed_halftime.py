# tests/test_feed_halftime.py
"""Feeds expose a halftime status and a termination bound; pure data (no pygame)."""
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed


def _script() -> dict:
    return {
        "status_by_minute": [(0, "live"), (48, "halftime")],
        "snapshots": [
            {"minute": 45, "stats": {"corner_kicks": 9}},
            {"minute": 48, "stats": {"corner_kicks": 10}},
        ],
    }


def test_mock_feed_reports_halftime_status():
    f = MockFeed(_script())
    assert f.match_status_at(48) == "halftime"
    assert f.match_status_at(46) == "live"


def test_last_known_minute_is_the_largest_minute_seen():
    f = MockFeed(_script())
    assert f.last_known_minute() == 48


def test_last_known_minute_is_zero_when_empty():
    assert MockFeed({}).last_known_minute() == 0


def test_delta_across_stoppage():
    f = MockFeed(_script())
    a = f.snapshot_at(45)
    b = f.snapshot_at(48)
    assert b.delta(a, "corner_kicks") == 1


def test_replay_feed_synthesizes_halftime_at_default_half_mark_when_absent():
    script = {"status_by_minute": [(0, "live"), (96, "finished")],
              "snapshots": [{"minute": 45, "stats": {}}], "meta": {}}
    f = ReplayFeed(script)
    assert f.match_status_at(45) == "halftime"
    assert f.match_status_at(44) == "live"


def test_replay_feed_honours_meta_first_half_end():
    script = {"status_by_minute": [(0, "live"), (96, "finished")],
              "snapshots": [{"minute": 48, "stats": {}}],
              "meta": {"first_half_end_minute": 48}}
    f = ReplayFeed(script)
    assert f.match_status_at(47) == "live"
    assert f.match_status_at(48) == "halftime"
