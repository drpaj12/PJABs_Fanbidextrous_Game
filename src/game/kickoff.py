# src/game/kickoff.py
"""Pure kickoff-timing logic for the live pre-game lobby. No pygame, no clock.

The wait screen passes in the kickoff timestamp (from the API fixture payload), the
current epoch, and the engine status; these helpers decide what to show and whether the
lead client should be polling yet:

  * too_early -> kickoff is further off than warn threshold; warn the player it is not
    live yet and do not spend API quota.
  * soon      -> within the warn window but before the start threshold; count down,
    still no polling.
  * active    -> within the start threshold, or the match is already under way; poll.
"""
from datetime import datetime, timezone
from typing import Optional

PHASE_TOO_EARLY = "too_early"
PHASE_SOON = "soon"
PHASE_ACTIVE = "active"

_SCHEDULED = "scheduled"


def seconds_to_kickoff(kickoff_iso: Optional[str], now_epoch: float) -> Optional[int]:
    """Seconds from now until kickoff (negative once kickoff has passed), or None if the
    timestamp is missing or unparseable. A naive timestamp is read as UTC."""
    if not kickoff_iso:
        return None
    try:
        dt = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() - now_epoch)


def kickoff_phase(seconds: Optional[int], status: str,
                  warn_seconds: int, start_seconds: int) -> str:
    """Classify the pre-game wait. A match that is no longer 'scheduled' (live/half/over)
    is always active, as is one whose kickoff time we do not know."""
    if status and status != _SCHEDULED:
        return PHASE_ACTIVE
    if seconds is None:
        return PHASE_ACTIVE
    if seconds > warn_seconds:
        return PHASE_TOO_EARLY
    if seconds > start_seconds:
        return PHASE_SOON
    return PHASE_ACTIVE


def format_countdown(seconds: int) -> str:
    """H:MM:SS once an hour or more out, else MM:SS. Clamped at 00:00 (never negative)."""
    s = max(0, int(seconds))
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
