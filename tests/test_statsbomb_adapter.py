# tests/test_statsbomb_adapter.py
"""Pure-function tests for the StatsBomb -> simulation adapter (no network)."""
from src.game.statsbomb_adapter import (
    STAT_FIELDS, cumulative_timeline, lineups_from_statsbomb, build_simulation,
    _broad_position, _short_name, _ascii_fold, _stat_increments,
)


def _shot(minute, outcome):
    return {"minute": minute, "type": {"name": "Shot"}, "shot": {"outcome": {"name": outcome}}}


def _corner(minute):
    return {"minute": minute, "type": {"name": "Pass"}, "pass": {"type": {"name": "Corner"}}}


def _save(minute):
    return {"minute": minute, "type": {"name": "Goal Keeper"},
            "goalkeeper": {"type": {"name": "Shot Saved"}}}


def _yellow(minute):
    return {"minute": minute, "type": {"name": "Foul Committed"},
            "foul_committed": {"card": {"name": "Yellow Card"}}}


def test_ascii_fold_strips_accents():
    assert _ascii_fold("Mbappe") == "Mbappe"
    assert _ascii_fold("Modrić") == "Modric"        # Modric with combining acute
    assert _ascii_fold("Kanté") == "Kante"


def test_short_name():
    assert _short_name("Kylian Mbappe") == "K. Mbappe"
    assert _short_name("Ronaldo") == "Ronaldo"


def test_broad_position_buckets():
    assert _broad_position("Goalkeeper") == "Goalkeeper"
    assert _broad_position("Right Back") == "Defender"
    assert _broad_position("Left Wing Back") == "Defender"
    assert _broad_position("Center Defensive Midfield") == "Midfielder"
    assert _broad_position("Center Forward") == "Attacker"
    assert _broad_position("Left Wing") == "Attacker"
    assert _broad_position("") == "Midfielder"


def test_stat_increments_classifies_each_event():
    assert _stat_increments(_shot(1, "Goal")) == ["shots_on_goal", "goals"]
    assert _stat_increments(_shot(1, "Saved")) == ["shots_on_goal"]
    assert _stat_increments(_shot(1, "Off T")) == []
    assert _stat_increments(_corner(1)) == ["corner_kicks"]
    assert _stat_increments(_save(1)) == ["goalkeeper_saves"]
    assert _stat_increments(_yellow(1)) == ["cards"]
    own_goal = {"minute": 5, "type": {"name": "Own Goal For"}}
    assert _stat_increments(own_goal) == ["goals"]


def test_cumulative_timeline_is_monotonic_and_per_minute():
    events = [_shot(3, "Goal"), _corner(3), _save(7), _yellow(7), _shot(7, "Saved")]
    snaps = cumulative_timeline(events, last_minute=10)
    assert len(snaps) == 11                               # minutes 0..10 inclusive
    assert snaps[0]["stats"] == {f: 0 for f in STAT_FIELDS}
    # at minute 3: one goal (also on target), one corner
    assert snaps[3]["stats"]["goals"] == 1
    assert snaps[3]["stats"]["shots_on_goal"] == 1
    assert snaps[3]["stats"]["corner_kicks"] == 1
    # at minute 7: +1 save, +1 card, +1 on-target shot (saved)
    assert snaps[7]["stats"]["goalkeeper_saves"] == 1
    assert snaps[7]["stats"]["cards"] == 1
    assert snaps[7]["stats"]["shots_on_goal"] == 2
    # cumulative never decreases
    for f in STAT_FIELDS:
        seq = [s["stats"][f] for s in snaps]
        assert seq == sorted(seq)


def test_lineups_starters_only_and_ascii():
    lineup_json = [{
        "team_name": "France",
        "lineup": [
            {"player_id": 3009, "player_name": "Kylian Mbappe Lottin",
             "player_nickname": "Kylian Mbappe", "jersey_number": 10,
             "positions": [{"position": "Right Wing", "from": "00:00"}]},
            {"player_id": 4001, "player_name": "Sub Player", "jersey_number": 22,
             "positions": [{"position": "Center Forward", "from": "75:00"}]},
        ],
    }]
    rows = lineups_from_statsbomb(lineup_json, starters_only=True)
    assert len(rows) == 1                                 # sub excluded
    # nickname preferred over the full legal name
    assert rows[0] == {"athlete_id": "sb-3009", "name": "K. Mbappe",
                       "broad_position": "Attacker", "team": "France", "jersey": 10}


def test_build_simulation_shape():
    events = [_shot(3, "Goal"), _corner(90)]
    lineup_json = [{"team_name": "France", "lineup": [
        {"player_id": 1, "player_name": "A B", "jersey_number": 1,
         "positions": [{"position": "Goalkeeper", "from": "00:00"}]}]}]
    sim = build_simulation(events, lineup_json, {"title": "Test"})
    assert sim["meta"]["title"] == "Test"
    assert sim["status_by_minute"] == [[0, "live"], [91, "finished"]]
    assert sim["snapshots"][-1]["minute"] == 90
    assert sim["snapshots"][-1]["stats"]["goals"] == 1
    assert len(sim["lineups"]) == 1
