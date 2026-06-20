# tests/test_schedule.py
"""Pure schedule logic: title fallback, kickoff parsing, status/label heuristics, the
rolling-window filter. No pygame; deterministic via explicit `now` epochs."""
from datetime import datetime, timedelta, timezone

from src.game.schedule import (ScheduledGame, load_schedule, game_status,
                               status_label, is_playable, visible_games)

_BASE = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
NOW = _BASE.timestamp()
_CFG = {"lookahead_hours": 48, "drop_after_hours": 4,
        "live_window_minutes": 150, "soon_minutes": 15}


def _at(**delta) -> str:
    return (_BASE + timedelta(**delta)).isoformat()


def _game(kickoff: str = "2026-06-20T17:00:00Z", home: str = "A", away: str = "B",
          **kw) -> ScheduledGame:
    base = dict(id=1, competition="WC", home=home, away=away, round="Group A",
                kickoff_utc=kickoff, kickoff_local="1:00 PM EDT")
    base.update(kw)
    return ScheduledGame(**base)


def test_title_uses_teams_when_known() -> None:
    assert _game(home="Brazil", away="Spain").title() == "Brazil v Spain"


def test_title_falls_back_to_round_when_teams_blank() -> None:
    assert _game(home="", away="", round="Round of 16 - Match 50").title() == \
        "Round of 16 - Match 50"


def test_kickoff_epoch_parses_z_and_offset_equally() -> None:
    z = _game(kickoff="2026-06-20T17:00:00Z").kickoff_epoch()
    off = _game(kickoff="2026-06-20T17:00:00+00:00").kickoff_epoch()
    assert z is not None and z == off


def test_kickoff_epoch_none_for_bad_string() -> None:
    assert _game(kickoff="not-a-date").kickoff_epoch() is None


def test_game_status_boundaries() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert game_status(g, k - 1, 150) == "upcoming"
    assert game_status(g, k, 150) == "live"
    assert game_status(g, k + 150 * 60 - 1, 150) == "live"
    assert game_status(g, k + 150 * 60, 150) == "final"


def test_status_label_units_and_states() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert status_label(g, k - 15 * 60, soon_minutes=10, live_window_minutes=150) == "in 15m"
    assert status_label(g, k - 2 * 3600, 15, 150) == "in 2h"
    assert status_label(g, k - 24 * 3600, 15, 150) == "in 1d"
    assert status_label(g, k - 10 * 60, 15, 150) == "soon"
    assert status_label(g, k - 15 * 60, 15, 150) == "soon"   # boundary: secs == soon
    assert status_label(g, k, 15, 150) == "LIVE NOW"
    assert status_label(g, k + 200 * 60, 15, 150) == "Final"


def test_is_playable_true_for_upcoming_and_live_false_for_final() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert is_playable(g, k - 60, 150) is True       # upcoming
    assert is_playable(g, k + 60, 150) is True        # live
    assert is_playable(g, k + 200 * 60, 150) is False  # final


def test_visible_games_window_and_sort() -> None:
    games = [
        _game(kickoff=_at(hours=47), home="Soon", away="Edge"),    # within lookahead
        _game(kickoff=_at(hours=49), home="Far", away="X"),         # beyond lookahead
        _game(kickoff=_at(hours=-3), home="Recent", away="Y"),      # within drop_after
        _game(kickoff=_at(hours=-5), home="Old", away="Z"),         # beyond drop_after
        _game(kickoff="bad-date", home="Broken", away="Q"),         # unparseable -> dropped
    ]
    vis = visible_games(games, NOW, _CFG)
    assert [g.title() for g in vis] == ["Recent v Y", "Soon v Edge"]


def test_load_schedule_parses_good_and_skips_malformed() -> None:
    raw = {"games": [
        {"id": 1, "competition": "WC", "home": "A", "away": "B", "round": "Group A",
         "kickoff_utc": "2026-06-20T17:00:00Z", "kickoff_local": "1:00 PM EDT"},
        {"id": 2, "competition": "WC", "home": "C", "away": "D",
         "kickoff_utc": "2026-06-20T18:00:00Z", "kickoff_local": "2:00 PM EDT"},  # no round
        {"id": 3, "competition": "WC", "home": "E", "away": "F", "round": "Group B",
         "kickoff_utc": "nope", "kickoff_local": "x"},                            # bad time
    ]}
    games = load_schedule(raw)
    assert len(games) == 1
    assert games[0].id == 1


def test_load_schedule_empty_or_missing_games() -> None:
    assert load_schedule({}) == []
    assert load_schedule({"games": []}) == []
