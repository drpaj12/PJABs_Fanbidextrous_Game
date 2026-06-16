# src/game/roster.py
"""A player's 6-athlete hand and the active-player rotation."""
from src.game.athlete import DraftedAthlete


class Roster:
    def __init__(self, athletes: list[DraftedAthlete]) -> None:
        self._athletes: list[DraftedAthlete] = list(athletes)
        self._used_ids: set[str] = set()

    def all_athletes(self) -> list[DraftedAthlete]:
        return list(self._athletes)

    def get(self, athlete_id: str) -> DraftedAthlete:
        for a in self._athletes:
            if a.athlete_id == athlete_id:
                return a
        raise KeyError(athlete_id)

    def available(self) -> list[DraftedAthlete]:
        return [a for a in self._athletes if a.athlete_id not in self._used_ids]

    def use(self, athlete_id: str) -> None:
        if athlete_id in self._used_ids:
            raise ValueError(f"athlete {athlete_id} already used this cycle")
        if athlete_id not in {a.athlete_id for a in self._athletes}:
            raise ValueError(f"athlete {athlete_id} not in roster")
        self._used_ids.add(athlete_id)
        if len(self._used_ids) >= len(self._athletes):
            self._used_ids.clear()
