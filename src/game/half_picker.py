# src/game/half_picker.py
"""Pure join-time decision: which half does a player entering NOW play?

Uses the RAW API-Football status short code (not the engine-mapped status) because the
decision must distinguish 1H / HT / 2H / FT, which the mapped vocabulary
(live / halftime / finished) collapses. No pygame, no I/O -- fully unit-testable.

See docs/superpowers/specs/2026-06-20-both-halves-design.md (section A)."""
from dataclasses import dataclass
from typing import Optional

_PREMATCH = {"NS", "TBD", "PST"}
_FIRST_HALF = "1H"
_HALFTIME = "HT"
_SECOND_HALF = "2H"


@dataclass(frozen=True)
class HalfChoice:
    half: Optional[int]   # 1, 2, or None when no playable half remains
    needs_wait: bool      # True when half == 2 but the 2H has not kicked off yet


def pick_half(status_short: str, elapsed: int, half_minutes: int,
              join_cutoff_minute: int) -> HalfChoice:
    """Decide the half to join. `elapsed` is the API match minute (1-90+);
    `join_cutoff_minute` is half-relative (e.g. 22)."""
    s = (status_short or "").upper()

    if s in _PREMATCH:
        return HalfChoice(1, False)

    if s == _FIRST_HALF:
        if elapsed < join_cutoff_minute:
            return HalfChoice(1, False)
        return HalfChoice(2, True)          # too late for 1H -> wait for 2H

    if s == _HALFTIME:
        return HalfChoice(2, True)

    if s == _SECOND_HALF:
        in_half = elapsed - half_minutes
        if in_half < join_cutoff_minute:
            return HalfChoice(2, False)
        return HalfChoice(None, False)      # too late for 2H -> no half left

    # Extra time, breaks, penalties, finished, and anything unknown: no regular half left.
    return HalfChoice(None, False)
