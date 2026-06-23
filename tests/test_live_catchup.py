# tests/test_live_catchup.py
"""Pure catch-up planning for the live crawl; no pygame (golden rule).

windows_elapsed answers "how many windows of THIS half has the live feed already fully
covered?" so the flow can auto-resolve them and land the player on the current live window.
It is the count form of half_clock.window_data_ready, scoped to the crawl's windows_per_half."""
from src.game.half_clock import HalfClock
from src.game.live_catchup import windows_elapsed


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
