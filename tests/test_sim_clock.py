# tests/test_sim_clock.py
"""Pure virtual clock for the realtime SIM harness (no pygame, golden rule)."""
from src.game.sim_clock import SimClock, kickoff_epoch_for
from src.game.match_clock import MatchClock
from src.game.half_clock import HalfClock


def test_realtime_advances_one_to_one():
    c = SimClock(virtual_start=1000.0, real_start=500.0, rate=1.0)
    # 90 real seconds elapsed -> 90 virtual seconds elapsed.
    assert c.now(590.0) == 1090.0


def test_realtime_at_start_is_virtual_start():
    c = SimClock(virtual_start=1000.0, real_start=500.0, rate=1.0)
    assert c.now(500.0) == 1000.0


def test_stepped_ignores_wall_clock():
    c = SimClock(virtual_start=1000.0, real_start=500.0, rate=0.0)
    # No matter how much real time passes, virtual time stays put until step().
    assert c.now(9999.0) == 1000.0


def test_stepped_advances_only_on_step():
    c = SimClock(virtual_start=1000.0, real_start=500.0, rate=0.0)
    c.step(15 * 60)            # jump one 15-minute window forward
    assert c.now(500.0) == 1000.0 + 15 * 60
    c.step(15 * 60)
    assert c.now(777.0) == 1000.0 + 30 * 60


def test_kickoff_offset_positive_is_in_the_past():
    # Arrive +20: kickoff happened 20 minutes ago.
    ko = kickoff_epoch_for(virtual_start=1000.0, offset_minutes=20)
    assert ko == 1000.0 - 20 * 60


def test_kickoff_offset_negative_is_in_the_future():
    # Arrive -5: kickoff is 5 minutes away.
    ko = kickoff_epoch_for(virtual_start=1000.0, offset_minutes=-5)
    assert ko == 1000.0 + 5 * 60


def test_offset_drives_match_minute_through_matchclock():
    # The whole point: feed the sim clock + offset kickoff into the SAME MatchClock the live
    # path uses, and the match minute reflects the arrival offset.
    vs = 1000.0
    clock = HalfClock(45, 15, total_windows=3)          # the dungeon clock
    c = SimClock(virtual_start=vs, real_start=vs, rate=1.0)
    ko = kickoff_epoch_for(vs, offset_minutes=20)
    mc = MatchClock(kickoff_epoch=ko, clock=clock)
    now = c.now(vs)                                     # at harness start
    assert mc.current_minute(now) == 20                 # arrived mid-W1
    assert mc.playing_window(now) == 2                  # 20' -> W2 (15-30') playing
    assert mc.editing_window(now) == 3                  # editing W3

    ko_pre = kickoff_epoch_for(vs, offset_minutes=-5)
    mc_pre = MatchClock(kickoff_epoch=ko_pre, clock=clock)
    assert mc_pre.current_minute(c.now(vs)) == 0        # pre-game
    assert mc_pre.playing_window(c.now(vs)) == 0
    assert mc_pre.editing_window(c.now(vs)) == 1
