# tests/test_half_clock.py
"""HalfClock is pure logic; no pygame here (golden rule)."""
from src.game.half_clock import HalfClock


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
