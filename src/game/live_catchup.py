# src/game/live_catchup.py
"""Pure catch-up planning for the LIVE crawl. No pygame, no I/O -- fully unit-testable.

When a client enters a live crawl after the match has already played some windows (or the
match is finished), those windows must auto-resolve so the player lands on the CURRENT live
window and is gated there. `windows_elapsed` answers how many windows of the current half the
live feed has already fully covered, so the flow knows how many to fast-forward."""
from src.game.half_clock import HalfClock, window_data_ready


def windows_elapsed(last_known_minute: int, clock: HalfClock, windows_per_half: int,
                    match_over: bool) -> int:
    """Count of this half's windows the live feed already fully covers (so they can be
    auto-resolved during catch-up). The count form of half_clock.window_data_ready, scoped to
    the crawl's `windows_per_half` (3) rather than the clock's 5-minute regular_windows.

    A finished/halftime match marks every window elapsed (no further data will arrive). The
    result is clamped to windows_per_half -- there is never a fractional or out-of-range
    window to fast-forward."""
    return sum(1 for w in range(1, windows_per_half + 1)
               if window_data_ready(last_known_minute, w, clock, match_over))
