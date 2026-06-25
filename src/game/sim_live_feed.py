# src/game/sim_live_feed.py
"""Present a recorded match (ReplayFeed) through the LiveFeed interface the dungeon LIVE
path consumes, but with the feed's VISIBLE PROGRESS governed by a virtual clock -- so the
sim feed "lags" exactly like a real API feed and catch-up / window_data_ready / force-resolve
behave identically. No pygame, no network (golden rule).

The recording numbers match minutes continuously (0..~95). The dungeon, however, plays two
45-minute halves and needs a per-half "whistle" at which the Extra-Time window (W3) resolves.
A continuous minute->status function cannot express that (minute 50 is "2H live", not
"halftime"), so the half context is injected as callables the flow wires to its live clock:

  minute_now()  -> current ABSOLUTE match minute (MatchClock.display_minute of virtual now)
  whistle_now() -> absolute minute the CURRENT half ends (45 for H1; full time for H2)
  final_now()   -> True if the current half is the last half (so the whistle = FINISHED)

Status reported: 'live' before the whistle; 'halftime' at/after the whistle in H1;
'finished' at/after it in H2. These are the engine status strings (config-driven).
"""
from typing import Callable, Optional
from src.game.sport_event import SportEvent, WindowSnapshot
from src.utils.constants import CONFIG

_HALFTIME = CONFIG["feed"]["halftime_status"]
_FINISHED = "finished"
_LIVE = "live"


class SimLiveFeed:
    def __init__(self, replay, minute_now: Callable[[], int],
                 whistle_now: Callable[[], int], final_now: Callable[[], bool],
                 kickoff_iso: str = "") -> None:
        self._replay = replay
        self._minute_now = minute_now
        self._whistle_now = whistle_now
        self._final_now = final_now
        self._kickoff_iso: Optional[str] = kickoff_iso or None
        self._meta = dict(getattr(replay, "meta", {}))
        self._max_minute = replay.last_known_minute()

    # -- progress governed by the virtual clock -----------------------------
    def last_known_minute(self) -> int:
        """How far the feed has data RIGHT NOW: the virtual match minute, clamped to the
        recording's end (it never reports data it would not yet have)."""
        return min(int(self._minute_now()), self._max_minute)

    def current_minute(self) -> int:
        """Live elapsed (absolute) match minute as the virtual clock sees it."""
        return int(self._minute_now())

    def snapshot_at(self, minute: int) -> WindowSnapshot:
        return self._replay.snapshot_at(min(int(minute), self._max_minute))

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    # -- status: per-half whistle, not the recording's continuous timeline --
    def _status(self) -> str:
        if int(self._minute_now()) < int(self._whistle_now()):
            return _LIVE
        return _FINISHED if self._final_now() else _HALFTIME

    def match_status(self) -> str:
        return self._status()

    def match_status_at(self, minute: int) -> str:
        if int(minute) < int(self._whistle_now()):
            return _LIVE
        return _FINISHED if self._final_now() else _HALFTIME

    def status_short(self) -> str:
        return self._status()

    # -- lineups / teams (from the recording) -------------------------------
    def lineups(self) -> list[dict]:
        return self._replay.lineups()

    def has_lineups(self) -> bool:
        return bool(self._replay.lineups())

    def home_team(self) -> str:
        return self._meta.get("home_team", "")

    def away_team(self) -> str:
        return self._meta.get("away_team", "")

    def home_goals(self) -> int:
        # The recording carries only aggregate goals (no home/away split), so the live
        # scoreline is cosmetic here; the [drpaj] log carries the real per-window data.
        return 0

    def away_goals(self) -> int:
        return 0

    def kickoff_iso(self) -> Optional[str]:
        return self._kickoff_iso

    def seed_kickoff(self, kickoff_iso: str) -> None:
        if kickoff_iso:
            self._kickoff_iso = kickoff_iso

    def record(self, snapshot: dict, minute: Optional[int] = None) -> None:
        """No-op: progress comes from the virtual clock, not pushed snapshots."""
        return
