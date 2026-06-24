# tests/test_half_clock.py
"""HalfClock is pure logic; no pygame here (golden rule)."""
from src.game.half_clock import HalfClock, window_data_ready


def _clock() -> HalfClock:
    return HalfClock(half_minutes=45, window_minutes=5)


def test_regular_windows_tile_the_half():
    assert _clock().regular_windows == 9


def test_extra_time_window_follows_the_regular_windows():
    assert _clock().extra_time_window == 10


def test_first_window_covers_zero_to_five():
    c = _clock()
    assert (c.window_start(1), c.window_end(1)) == (0, 5)


def test_last_regular_window_covers_forty_to_forty_five():
    c = _clock()
    assert (c.window_start(9), c.window_end(9)) == (40, 45)


def test_regular_windows_are_not_extra_time():
    assert _clock().is_extra_time(9) is False


def test_the_tenth_window_is_extra_time():
    assert _clock().is_extra_time(10) is True


def test_extra_time_starts_at_the_half_mark():
    assert _clock().window_start(10) == 45


def test_half_over_only_on_the_halftime_status():
    assert HalfClock.is_half_over("halftime", "halftime") is True
    assert HalfClock.is_half_over("live", "halftime") is False


def test_first_half_offset_is_zero_by_default() -> None:
    c = HalfClock(45, 5)
    assert c.start_minute == 0
    assert c.window_start(1) == 0
    assert c.window_end(1) == 5
    assert c.window_end(9) == 45


def test_second_half_offsets_to_absolute_minutes() -> None:
    c = HalfClock(45, 5, start_minute=45)
    assert c.window_start(1) == 45
    assert c.window_end(1) == 50
    assert c.window_end(9) == 90


def test_second_half_extra_time_starts_at_ninety() -> None:
    c = HalfClock(45, 5, start_minute=45)
    assert c.window_start(c.extra_time_window) == 90
    assert c.regular_windows == 9
    assert c.extra_time_window == 10


# -- total_windows override: the dungeon's "last window absorbs extra time" --

def test_total_windows_makes_the_last_window_extra_time() -> None:
    # The dungeon wants exactly 3 windows per half, the 3rd absorbing stoppage/extra time --
    # NOT 3 regular windows plus a separate 4th ET window. total_windows expresses that.
    c = HalfClock(45, 15, total_windows=3)
    assert c.regular_windows == 2
    assert c.extra_time_window == 3


def test_total_windows_keeps_window_minute_tiling() -> None:
    c = HalfClock(45, 15, total_windows=3)
    assert (c.window_start(1), c.window_end(1)) == (0, 15)
    assert (c.window_start(2), c.window_end(2)) == (15, 30)
    assert c.window_start(3) == 30          # W3 begins at 30' and runs to the whistle


def test_total_windows_last_window_is_extra_time() -> None:
    c = HalfClock(45, 15, total_windows=3)
    assert c.is_extra_time(2) is False
    assert c.is_extra_time(3) is True


def test_total_windows_last_window_ready_only_when_match_over() -> None:
    # W3 is the ET absorber: it must NOT resolve at a clock boundary (stoppage keeps playing),
    # only when the half whistle blows -- so a live crawl never overshoots W3 into the recap.
    c = HalfClock(45, 15, total_windows=3)
    assert window_data_ready(99, 3, c, match_over=False) is False
    assert window_data_ready(99, 3, c, match_over=True) is True
    assert window_data_ready(31, 2, c, match_over=False) is True   # W2 still resolves at 30'


def test_total_windows_second_half_offsets() -> None:
    c = HalfClock(45, 15, start_minute=45, total_windows=3)
    assert (c.window_start(1), c.window_end(1)) == (45, 60)
    assert (c.window_start(2), c.window_end(2)) == (60, 75)
    assert c.window_start(3) == 75
    assert c.is_extra_time(3) is True


def test_default_clock_unchanged_without_total_windows() -> None:
    # The single-player live path (LiveFlow) keeps 3 regular windows + a 4th ET window.
    c = HalfClock(45, 15)
    assert c.regular_windows == 3
    assert c.extra_time_window == 4


# -- window_data_ready: the live-crawl resolution gate ----------------------

def test_window_not_ready_until_feed_covers_its_end() -> None:
    c = _clock()  # window 2 ends at minute 10
    assert window_data_ready(9, 2, c, match_over=False) is False
    assert window_data_ready(10, 2, c, match_over=False) is True
    assert window_data_ready(12, 2, c, match_over=False) is True


def test_window_not_ready_at_bare_clock_boundary_with_stale_feed() -> None:
    # The clock crossed into window 3 (real time >= 10') but the feed minute still lags at 8':
    # window 2 (ends 10') must NOT resolve yet -- this is the stale-zeros bug being prevented.
    c = _clock()
    assert window_data_ready(8, 2, c, match_over=False) is False


def test_match_over_forces_ready_even_with_stale_feed() -> None:
    c = _clock()
    assert window_data_ready(3, 5, c, match_over=True) is True


def test_extra_time_window_only_ready_when_match_over() -> None:
    c = _clock()  # extra-time window is 10
    assert window_data_ready(99, 10, c, match_over=False) is False
    assert window_data_ready(99, 10, c, match_over=True) is True


def test_second_half_window_ready_uses_absolute_minutes() -> None:
    c = HalfClock(45, 5, start_minute=45)  # window 1 ends at minute 50
    assert window_data_ready(48, 1, c, match_over=False) is False
    assert window_data_ready(50, 1, c, match_over=False) is True
