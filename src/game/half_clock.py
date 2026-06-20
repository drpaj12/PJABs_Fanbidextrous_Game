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
