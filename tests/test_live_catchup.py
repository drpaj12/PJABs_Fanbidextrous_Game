# tests/test_live_catchup.py
"""Pure catch-up planning for the live crawl; no pygame (golden rule).

windows_elapsed answers "how many windows of THIS half has the live feed already fully
covered?" so the flow can auto-resolve them and land the player on the current live window.
It is the count form of half_clock.window_data_ready, scoped to the crawl's windows_per_half."""
from src.game.half_clock import HalfClock
from src.game.live_catchup import windows_elapsed, initial_catch_up_target


def _h1() -> HalfClock:
    # The dungeon party crawl: 45-minute half, 15-minute windows -> 3 windows per half.
    return HalfClock(half_minutes=45, window_minutes=15)


def _h2() -> HalfClock:
    # Second half re-anchored to absolute minutes 45..90.
    return HalfClock(half_minutes=45, window_minutes=15, start_minute=45)


def test_nothing_elapsed_before_first_window_end():
    # minute 8: window 1 ends at 15, feed has not covered it yet.
    assert windows_elapsed(8, _h1(), windows_per_half=3, match_over=False) == 0


def test_one_window_elapsed_midway():
    # minute 20: window 1 (ends 15) is covered, window 2 (ends 30) is not.
    assert windows_elapsed(20, _h1(), windows_per_half=3, match_over=False) == 1


def test_exact_boundary_counts_the_completed_window():
    # minute 30: windows 1 (15) and 2 (30) are covered, window 3 (45) is not.
    assert windows_elapsed(30, _h1(), windows_per_half=3, match_over=False) == 2


def test_all_windows_elapsed_when_feed_past_half_end():
    assert windows_elapsed(45, _h1(), windows_per_half=3, match_over=False) == 3


def test_match_over_marks_every_window_elapsed_even_with_stale_feed():
    # Finished match: no more data will arrive, so all windows are caught up.
    assert windows_elapsed(3, _h1(), windows_per_half=3, match_over=True) == 3


def test_second_half_uses_absolute_minutes():
    # minute 70 in H2: window 1 ends at 60 (covered), window 2 ends at 75 (not).
    assert windows_elapsed(70, _h2(), windows_per_half=3, match_over=False) == 1


def test_count_never_exceeds_windows_per_half():
    assert windows_elapsed(200, _h1(), windows_per_half=3, match_over=False) == 3


# -- initial_catch_up_target: late-join defaulting on the FIRST live window --
# A player whose shop finishes after kickoff can never have locked the windows already in
# play -- those predictions "had to be locked in before the game". On the first live window of
# a half the flow defaults every such window (by editing_window - 1) and lands the player on
# the current editable window, instead of trapping them on a window the match already started.

def test_on_time_start_defaults_nothing():
    # Shop finished before kickoff: editing_window 1, no window has started -> default nothing.
    assert initial_catch_up_target(editing_window=1, windows_per_half=3, base_elapsed=0) == 0


def test_late_join_mid_first_window_defaults_w1_and_lands_on_w2():
    # Joined at 8' (W1 in play, editing_window 2): W1's deadline passed -> default 1, land W2.
    assert initial_catch_up_target(editing_window=2, windows_per_half=3, base_elapsed=0) == 1


def test_late_join_in_second_window_defaults_w1_and_w2():
    # Joined at 20' (W2 in play, editing_window 3): default W1+W2, land W3.
    assert initial_catch_up_target(editing_window=3, windows_per_half=3, base_elapsed=0) == 2


def test_never_defaults_the_extra_time_window():
    # Even joining deep in stoppage (editing pinned at the ET window 3) never auto-resolves W3 --
    # the last window only resolves at the whistle, so the player still plays it.
    assert initial_catch_up_target(editing_window=3, windows_per_half=3, base_elapsed=0) == 2
    assert initial_catch_up_target(editing_window=4, windows_per_half=3, base_elapsed=0) == 2


def test_takes_the_max_of_deadline_and_data_ready():
    # If more windows are already data-ready than the editing clock implies, honor the larger
    # count (a finished/halftime feed reports all windows elapsed via base_elapsed).
    assert initial_catch_up_target(editing_window=2, windows_per_half=3, base_elapsed=3) == 3


def test_dungeon_clock_w3_is_extra_time_not_elapsed_until_whistle():
    # The dungeon's own clock (3 windows, W3 = ET) must report W3 NOT elapsed at the 45' mark --
    # only when the match is over. This is what stops the live crawl overshooting into the recap.
    et_clock = HalfClock(45, 15, total_windows=3)
    assert windows_elapsed(45, et_clock, windows_per_half=3, match_over=False) == 2
    assert windows_elapsed(45, et_clock, windows_per_half=3, match_over=True) == 3
