# src/game/replay_feed.py
"""Replay a recorded real match (a simulation file) through the EventFeed interface.

A simulation file is the same script schema MockFeed consumes (status_by_minute +
snapshots + lineups) plus a `meta` block describing the match. Generated offline from
StatsBomb open data by scripts/build_simulation_from_statsbomb.py; loaded here for
offline/deterministic play.

Recorded sims predate the half-game and carry no half-time status, so we synthesize
one: at `meta.first_half_end_minute` if present, else at the configured half mark.
The flow still discovers it by polling -- this only guarantees there is something to
discover.
"""
from src.game.mock_feed import MockFeed
from src.utils.constants import CONFIG, load_data

_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_HALF_MIN = CONFIG["game"]["half_minutes"]


class ReplayFeed(MockFeed):
    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.meta: dict = dict(script.get("meta", {}))
        if not any(s == _HALFTIME_STATUS for _, s in self._status):
            ht = int(self.meta.get("first_half_end_minute", _HALF_MIN))
            self._status = sorted(self._status + [(ht, _HALFTIME_STATUS)])

    @classmethod
    def from_file(cls, rel_path: str) -> "ReplayFeed":
        """Load a simulation file by repo-relative path (e.g. assets/data/simulations/x.json)."""
        return cls(load_data(rel_path))
