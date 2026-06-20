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
        advancing with no API input. Half-relative (0..45); see display_minute for the
        absolute match minute."""
        return max(0, int((now - self.kickoff_epoch) // 60))

    def display_minute(self, now: float) -> int:
        """Absolute match minute for display (offsets current_minute by the half's
        start_minute), so the second half reads 46'-90' instead of 1'-45'."""
        return self.clock.start_minute + self.current_minute(now)

    def realign(self, api_minute_in_half: int, now: float,
                threshold_seconds: float) -> "MatchClock":
        """Snap the wall-clock anchor to the API's reported minute when our estimate has
        drifted past threshold_seconds; otherwise return self unchanged. The initial anchor
        (config kickoff for 1H, an estimate for 2H) self-corrects each poll.

        api_minute_in_half is the API match minute mapped into this half (0-based:
        max(0, api_elapsed - clock.start_minute)). We compare against the MIDPOINT of that
        integer minute so a clock sitting mid-minute is not treated as drifted."""
        our_elapsed = now - self.kickoff_epoch
        api_elapsed = (api_minute_in_half + 0.5) * 60
        if abs(our_elapsed - api_elapsed) > threshold_seconds:
            return MatchClock(now - api_elapsed, self.clock)
        return self

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
