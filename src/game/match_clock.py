# src/game/match_clock.py
"""Pure wall-clock match engine: maps a kickoff time and 'now' to the live match minute
and to which 5-minute window is playing vs. which the player is editing.

No pygame, no I/O, no real clock -- 'now' is passed in (epoch seconds) so it is fully
unit-testable and deterministic. Window numbering and the Extra-Time index come from the
composed HalfClock. The player always edits one window ahead of the one playing
(see the spec's timing table)."""
from dataclasses import dataclass
from src.game.half_clock import HalfClock


@dataclass(frozen=True)
class MatchClock:
    kickoff_epoch: float
    clock: HalfClock

    def current_minute(self, now: float) -> int:
        """Live match minute, clamped at 0 before kickoff. Pure wall-clock -- it keeps
        advancing with no API input."""
        return max(0, int((now - self.kickoff_epoch) // 60))

    def playing_window(self, now: float) -> int:
        """1-based index of the window currently in progress; 0 before kickoff. Caps at the
        Extra-Time window (stoppage keeps the clock past 45')."""
        if now < self.kickoff_epoch:
            return 0
        w = self.current_minute(now) // self.clock.window_minutes + 1
        return min(w, self.clock.extra_time_window)

    def editing_window(self, now: float) -> int:
        """The window the player fills in: one ahead of the playing window, capped at ET
        (while ET plays there is nothing further to edit)."""
        return min(self.playing_window(now) + 1, self.clock.extra_time_window)

    def windows_entered(self, prev_now: float, now: float) -> list[int]:
        """Window indices newly ENTERED in (prev_now, now]. Normally [] or one index at a
        boundary; returns several if a backgrounded tab skipped boundaries. The caller
        locks+resolves each in order. ET is entered by time at 45'; its RESOLUTION is
        status-driven (halftime) and handled by the caller, not here."""
        prev = self.playing_window(prev_now)
        cur = self.playing_window(now)
        return list(range(prev + 1, cur + 1))
