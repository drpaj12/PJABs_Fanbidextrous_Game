# tests/test_live_schedule.py
"""Window-sizing for live play: lobby + remaining scored windows."""
import pytest
from src.game.half_clock import HalfClock
from src.game.live_schedule import live_plan

CLOCK = HalfClock(half_minutes=45, window_minutes=5)   # 9 regular windows, ET = 10
FULL = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


@pytest.mark.parametrize("elapsed,status,lobby,scored", [
    (0,  "scheduled", 0,    FULL),                 # pre-match: draft pre-kickoff, full half
    (0,  "live",      0,    FULL),                 # kickoff instant treated as pre-match
    (1,  "live",      1,    [2, 3, 4, 5, 6, 7, 8, 9, 10]),
    (23, "live",      5,    [6, 7, 8, 9, 10]),     # join at 23' -> 5 scored windows
    (43, "live",      9,    [10]),                 # late join -> Extra-Time only
])
def test_live_plan_in_first_half(elapsed, status, lobby, scored):
    plan = live_plan(elapsed, status, CLOCK)
    assert plan.lobby_window == lobby
    assert plan.scored_windows == scored


@pytest.mark.parametrize("elapsed,status", [
    (45, "halftime"), (46, "live"), (60, "live"), (90, "finished"), (0, "finished")])
def test_half_over_has_no_scored_windows(elapsed, status):
    plan = live_plan(elapsed, status, CLOCK)
    assert plan.lobby_window is None
    assert plan.scored_windows == []


# -- Second-half contract -------------------------------------------------------
# live_plan is offset-agnostic: the caller passes HALF-RELATIVE elapsed (0..45) and a
# clock whose start_minute marks the half. Window indices stay 1-based per half, so a 2H
# clock (start_minute=45) must produce exactly the same lobby/scored plan as a 1H clock
# given the same half-relative elapsed. These guard the start_live launch_half(2) path,
# which subtracts the half offset before calling live_plan.
CLOCK_2H = HalfClock(half_minutes=45, window_minutes=5, start_minute=45)


@pytest.mark.parametrize("elapsed_in_half,status,lobby,scored", [
    (0,  "live", 0,    FULL),                        # second-half kickoff instant
    (1,  "live", 1,    [2, 3, 4, 5, 6, 7, 8, 9, 10]),
    (23, "live", 5,    [6, 7, 8, 9, 10]),            # join 23' into the half (real 68')
    (43, "live", 9,    [10]),                        # late: Extra-Time only
])
def test_live_plan_second_half_matches_first(elapsed_in_half, status, lobby, scored):
    plan = live_plan(elapsed_in_half, status, CLOCK_2H)
    assert plan.lobby_window == lobby
    assert plan.scored_windows == scored


@pytest.mark.parametrize("elapsed_in_half,status", [
    (45, "finished"), (46, "live"), (50, "finished")])
def test_second_half_over_has_no_scored_windows(elapsed_in_half, status):
    plan = live_plan(elapsed_in_half, status, CLOCK_2H)
    assert plan.lobby_window is None
    assert plan.scored_windows == []
