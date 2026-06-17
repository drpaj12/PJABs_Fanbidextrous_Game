# tests/test_replay_feed.py
"""ReplayFeed behaves like an EventFeed over a simulation script."""
from src.game.replay_feed import ReplayFeed


def _script():
    return {
        "meta": {"title": "France 4-2 Croatia", "home_team": "France", "away_team": "Croatia"},
        "status_by_minute": [[0, "live"], [91, "finished"]],
        "snapshots": [
            {"minute": 0, "stats": {"corner_kicks": 0, "goals": 0}},
            {"minute": 5, "stats": {"corner_kicks": 3, "goals": 1}},
            {"minute": 90, "stats": {"corner_kicks": 9, "goals": 6}},
        ],
        "lineups": [{"athlete_id": "sb-1", "name": "K. Mbappe",
                     "broad_position": "Attacker", "team": "France", "jersey": 10}],
    }


def test_meta_exposed():
    feed = ReplayFeed(_script())
    assert feed.meta["title"] == "France 4-2 Croatia"


def test_snapshot_at_returns_nearest_earlier():
    feed = ReplayFeed(_script())
    assert feed.snapshot_at(5).stats["corner_kicks"] == 3
    assert feed.snapshot_at(7).stats["corner_kicks"] == 3      # nearest earlier
    assert feed.snapshot_at(90).stats["goals"] == 6


def test_status_transition():
    feed = ReplayFeed(_script())
    assert feed.match_status_at(10) == "live"
    assert feed.match_status_at(91) == "finished"
    assert feed.match_status() == "finished"


def test_lineups_passthrough():
    feed = ReplayFeed(_script())
    rows = feed.lineups()
    assert rows[0]["name"] == "K. Mbappe"
