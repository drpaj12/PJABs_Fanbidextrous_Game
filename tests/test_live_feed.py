# tests/test_live_feed.py
"""LiveFeed adapts API-Football v3 relay snapshots into the EventFeed interface."""
import json
from pathlib import Path
from src.game.live_feed import LiveFeed

FIX = Path(__file__).parent / "fixtures"


def _lineups() -> dict:
    return json.loads((FIX / "apifootball_lineups_sample.json").read_text())


def _stats(corners: int, shots: int, saves: int) -> dict:
    return {"response": [{"team": {"name": "Canada"}, "statistics": [
        {"type": "Corner Kicks", "value": corners},
        {"type": "Shots on Goal", "value": shots},
        {"type": "Goalkeeper Saves", "value": saves},
    ]}]}


def _fixture(short: str, elapsed: int, gh: int, ga: int) -> dict:
    return {"response": [{
        "fixture": {"id": 1, "status": {"short": short, "elapsed": elapsed}},
        "teams": {"home": {"name": "Canada"}, "away": {"name": "X"}},
        "goals": {"home": gh, "away": ga}}]}


def _snap(short, elapsed, corners, shots, saves, gh, ga, lineups=True) -> dict:
    return {"lineups": _lineups() if lineups else {"response": []},
            "statistics": _stats(corners, shots, saves),
            "fixture": _fixture(short, elapsed, gh, ga)}


def test_lineups_startxi_only():
    feed = LiveFeed(_snap("1H", 10, 1, 1, 0, 0, 0))
    rows = feed.lineups()
    ids = {r["athlete_id"] for r in rows}
    assert "sccr-501" in ids        # a starter
    assert "sccr-503" not in ids    # a substitute -- excluded from the draft pool
    assert all(r["broad_position"] for r in rows)


def test_goals_come_from_fixture_score():
    feed = LiveFeed(_snap("1H", 20, 4, 4, 2, 1, 1))
    assert feed.snapshot_at(20).stats["goals"] == 2


def test_window_delta_between_minutes():
    feed = LiveFeed()
    feed.record(_snap("1H", 20, 4, 4, 2, 1, 0))
    feed.record(_snap("1H", 25, 6, 7, 3, 1, 1))
    a, b = feed.snapshot_at(20), feed.snapshot_at(25)
    assert b.delta(a, "corner_kicks") == 2
    assert b.delta(a, "shots_on_goal") == 3
    assert b.delta(a, "goals") == 1


def test_snapshot_at_returns_nearest_earlier():
    feed = LiveFeed()
    feed.record(_snap("1H", 20, 4, 4, 2, 0, 0))
    assert feed.snapshot_at(23).stats["corner_kicks"] == 4


def test_status_and_minute_mapping():
    ht = LiveFeed(_snap("HT", 45, 9, 9, 4, 1, 1))
    assert ht.match_status() == "halftime"
    assert ht.current_minute() == 45
    assert LiveFeed(_snap("1H", 12, 1, 1, 0, 0, 0)).match_status() == "live"


def test_prematch_has_no_lineups():
    feed = LiveFeed(_snap("NS", 0, 0, 0, 0, 0, 0, lineups=False))
    assert feed.has_lineups() is False
    assert feed.match_status() == "scheduled"


def test_empty_poll_does_not_wipe_seen_lineups():
    feed = LiveFeed(_snap("1H", 10, 1, 1, 0, 0, 0))
    feed.record(_snap("1H", 15, 2, 2, 1, 0, 0, lineups=False))  # later poll, lineups dropped
    assert feed.has_lineups() is True


def test_team_names_from_fixture():
    feed = LiveFeed(_snap("1H", 10, 1, 1, 0, 0, 0))
    assert feed.home_team() == "Canada"
    assert feed.away_team() == "X"


def test_kickoff_iso_and_status_short_from_fixture():
    snap = _snap("NS", 0, 0, 0, 0, 0, 0, lineups=False)
    snap["fixture"]["response"][0]["fixture"]["date"] = "2026-06-20T18:00:00+00:00"
    feed = LiveFeed(snap)
    assert feed.kickoff_iso() == "2026-06-20T18:00:00+00:00"
    assert feed.status_short() == "NS"


def test_kickoff_iso_none_until_seen():
    assert LiveFeed().kickoff_iso() is None
