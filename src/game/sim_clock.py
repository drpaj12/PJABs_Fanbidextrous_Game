# src/game/sim_clock.py
"""Virtual match clock for the realtime SIM harness. No pygame, no real clock read --
'now' is computed from a real timestamp passed in, so it is fully unit-testable.

The harness drives the EXACT live dungeon path by substituting this clock for time.time().
Two speed modes:
  rate == 1.0  -> REALTIME: virtual time advances 1:1 with the wall clock.
  rate == 0.0  -> STEPPED ("accelerated"): virtual time only moves when step() is called
                  (wired to the existing SIM 'F' hotkey), so the developer walks the flow.

Kickoff is positioned by the chosen arrival OFFSET, which the flow turns into a
kickoff_epoch (NOT stored here -- the flow owns kickoff_epoch exactly like the live path):

    kickoff_epoch = virtual_start - offset_minutes * 60
      offset +20 -> kickoff 20' in the past  -> current_minute == 20 at start (mid-W1)
      offset  -5 -> kickoff 5' in the future  -> pre-game (playing_window 0, editing 1)
"""
from dataclasses import dataclass


@dataclass
class SimClock:
    virtual_start: float        # virtual epoch at harness start
    real_start: float           # real epoch (time.time()) captured at harness start
    rate: float = 1.0           # 1.0 = realtime ; 0.0 = stepped
    manual_seconds: float = 0.0  # accumulated step() seconds (stepped mode only)

    def now(self, real_now: float) -> float:
        """Virtual 'now' (epoch seconds) for a given real wall-clock reading. In stepped mode
        the wall clock is ignored -- only step() advances time."""
        if self.rate == 0.0:
            return self.virtual_start + self.manual_seconds
        return self.virtual_start + (real_now - self.real_start) * self.rate

    def step(self, seconds: float) -> None:
        """Advance virtual time by `seconds` (stepped mode). No-op semantics in realtime mode
        are left to the caller -- the harness only calls step() when rate == 0.0."""
        self.manual_seconds += seconds


def kickoff_epoch_for(virtual_start: float, offset_minutes: float) -> float:
    """Where kickoff sits on the virtual timeline for a chosen arrival offset.
    Positive offset = arrive AFTER kickoff (kickoff in the past); negative = before."""
    return virtual_start - offset_minutes * 60
