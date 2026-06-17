# src/game/replay_feed.py
"""Replay a recorded real match (a simulation file) through the EventFeed interface.

A simulation file is the same script schema MockFeed consumes (status_by_minute + snapshots
+ lineups) plus a `meta` block describing the match. Generated offline from StatsBomb open
data by scripts/build_simulation_from_statsbomb.py; loaded here for offline/deterministic play.
"""
from src.game.mock_feed import MockFeed
from src.utils.constants import load_data


class ReplayFeed(MockFeed):
    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.meta: dict = dict(script.get("meta", {}))

    @classmethod
    def from_file(cls, rel_path: str) -> "ReplayFeed":
        """Load a simulation file by repo-relative path (e.g. assets/data/simulations/x.json)."""
        return cls(load_data(rel_path))
