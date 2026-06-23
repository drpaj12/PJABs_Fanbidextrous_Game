# src/game/half_clock.py
"""Pure-logic clock for a single half: window boundaries, extra-time detection,
and the half-over test. No pygame, no I/O -- driven entirely by the config numbers
passed in, so it is fully unit-testable.

A half is `half_minutes` long, diced into fixed `window_minutes` windows. With a
45-minute half and 5-minute windows that is 9 regular windows (numbered 1..9,
covering minutes 0..45). One extra window -- index `regular_windows + 1` -- is the
Extra-Time window: it begins at the 45th minute and runs until the live feed
reports the half is over. Its end minute is therefore NOT computable here; the
caller discovers it by polling and asking is_half_over().
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class HalfClock:
    half_minutes: int
    window_minutes: int
    start_minute: int = 0   # 0 for the first half, 45 for the second (absolute match minutes)

    @property
    def regular_windows(self) -> int:
        """Number of fixed windows that tile the half (45 // 5 = 9)."""
        return self.half_minutes // self.window_minutes

    @property
    def extra_time_window(self) -> int:
        """1-based index of the single Extra-Time window (10 for a 9-window half)."""
        return self.regular_windows + 1

    def is_extra_time(self, window: int) -> bool:
        return window >= self.extra_time_window

    def window_start(self, window: int) -> int:
        """First (absolute) match minute of a window. Valid for regular and ET windows.
        Offset by start_minute so the second half returns 45.. instead of 0.."""
        return self.start_minute + (window - 1) * self.window_minutes

    def window_end(self, window: int) -> int:
        """Last (absolute) match minute of a REGULAR window. Meaningless for ET (end is
        discovered). Offset by start_minute (45.. in the second half)."""
        return self.start_minute + window * self.window_minutes

    @staticmethod
    def is_half_over(status: str, halftime_status: str) -> bool:
        return status == halftime_status


def window_data_ready(last_known_minute: int, window: int, clock: HalfClock,
                      match_over: bool) -> bool:
    """Whether a live crawl window may resolve yet -- i.e. the feed actually holds the data
    for that window. A window must NOT resolve at the bare clock boundary: the live feed
    minute lags real time, so resolving early grades the picks against stale cumulative
    totals (every stat reads delta ~0 -> every prediction looks like a big miss). Gating on
    data availability makes the actuals query happen WITHIN the window, like the offline
    crawl. Mirrors live_play_screen.windows_ready() for the single-player live path.

    Ready when the match has ended/halftime (no further data will arrive), else when the feed
    covers the window's end minute. The Extra-Time window has no computable end minute, so it
    resolves only once the match is over."""
    if match_over:
        return True
    if clock.is_extra_time(window):
        return False
    return last_known_minute >= clock.window_end(window)
