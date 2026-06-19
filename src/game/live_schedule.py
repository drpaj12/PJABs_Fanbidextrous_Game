# src/game/live_schedule.py
"""Pure window-sizing for live play.

Given the live match minute + engine status, decide which window is the (unscored) lobby
-- the in-progress window players draft and make their first predictions in -- and which
windows remain to be played and scored. No pygame, no I/O: all boundary numbers come from
the HalfClock built from config.

See docs/superpowers/specs/2026-06-19-live-single-player-design.md ("remaining-half model").
"""
from dataclasses import dataclass
from typing import Optional
from src.game.half_clock import HalfClock

_LIVE = "live"
_SCHEDULED = "scheduled"
_PREKICKOFF_LOBBY = 0   # sentinel: lobby is the pre-kickoff buildup, not a real window


@dataclass(frozen=True)
class LivePlan:
    lobby_window: Optional[int]   # window for draft + first predictions; None if half over
    scored_windows: list[int]     # windows to play in order (regular... then Extra-Time)


def live_plan(elapsed: int, status: str, clock: HalfClock) -> LivePlan:
    """Compute the lobby + remaining scored windows for a player joining now."""
    et = clock.extra_time_window
    full_half = list(range(1, clock.regular_windows + 1)) + [et]

    # Pre-match (or the instant of kickoff): the whole half is ahead; draft pre-kickoff.
    if status == _SCHEDULED or (status == _LIVE and elapsed <= 0):
        return LivePlan(lobby_window=_PREKICKOFF_LOBBY, scored_windows=full_half)

    # First half already over (halftime / second half / finished / clock past the half).
    if status != _LIVE or elapsed >= clock.half_minutes:
        return LivePlan(lobby_window=None, scored_windows=[])

    # Live inside the first half: the window containing `elapsed` is the lobby; every
    # later regular window plus Extra-Time is scored.
    lobby = elapsed // clock.window_minutes + 1
    scored = list(range(lobby + 1, clock.regular_windows + 1)) + [et]
    return LivePlan(lobby_window=lobby, scored_windows=scored)
