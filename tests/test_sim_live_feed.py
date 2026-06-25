# tests/test_sim_live_feed.py
"""SimLiveFeed presents a recorded match through the LiveFeed interface, with progress
governed by a virtual clock and a per-half whistle (no pygame, golden rule)."""
from src.game.sim_live_feed import SimLiveFeed
from src.game.replay_feed import ReplayFeed
from src.utils.constants import CONFIG

_HALFTIME = CONFIG["feed"]["halftime_status"]
_SIM = "assets/data/simulations/wc2018_final_fra_cro.json"


def _replay() -> ReplayFeed:
    return ReplayFeed.from_file(_SIM)


def _feed(minute, whistle=45, final=False):
    # minute/whistle/final are plain values here; the flow injects live lambdas.
    return SimLiveFeed(_replay(), minute_now=lambda: minute,
                       whistle_now=lambda: whistle, final_now=lambda: final)


def test_last_known_minute_tracks_the_clock():
    assert _feed(minute=12).last_known_minute() == 12
    assert _feed(minute=30).last_known_minute() == 30


def test_last_known_minute_clamps_at_recording_end():
    # The FRA-CRO recording ends ~95'; a clock past that cannot conjure later data.
    f = _feed(minute=200)
    assert f.last_known_minute() <= 96
    assert f.last_known_minute() >= 90


def test_snapshot_delegates_to_the_recording():
    f = _feed(minute=90)
    # Cumulative stats grow over the match: minute 0 has fewer corners than minute 90.
    s0 = f.snapshot_at(0).stats.get("corner_kicks", 0)
    s90 = f.snapshot_at(90).stats.get("corner_kicks", 0)
    assert s90 >= s0
    assert s90 > 0


def test_status_is_live_before_the_whistle():
    assert _feed(minute=20, whistle=45, final=False).match_status() == "live"


def test_first_half_whistle_reports_halftime():
    # At/after the H1 whistle (45) in a non-final half -> halftime, so W3 resolves.
    assert _feed(minute=45, whistle=45, final=False).match_status() == _HALFTIME
    assert _feed(minute=50, whistle=45, final=False).match_status() == _HALFTIME


def test_second_half_play_is_live_not_halftime():
    # Crucial: in H2 (whistle = full time), minute 50 must be LIVE, never halftime --
    # otherwise catch-up would treat the whole half as over and overshoot to the recap.
    f = _feed(minute=50, whistle=95, final=True)
    assert f.match_status() == "live"


def test_final_half_whistle_reports_finished():
    assert _feed(minute=95, whistle=95, final=True).match_status() == "finished"


def test_teams_and_lineups_from_recording():
    f = _feed(minute=10)
    assert f.home_team() == "France"
    assert f.away_team() == "Croatia"
    assert f.has_lineups()
    assert len(f.lineups()) > 0


def test_record_is_a_noop():
    f = _feed(minute=10)
    f.record({"anything": True})
    assert f.last_known_minute() == 10
