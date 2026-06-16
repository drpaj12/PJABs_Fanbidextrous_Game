# src/game/sport_event.py
"""Sport-agnostic event and per-window stat snapshot. Zero pygame, zero soccer literals."""
from dataclasses import dataclass, field


@dataclass
class SportEvent:
    event_id: str
    event_type: str
    athlete_ids: list[str] = field(default_factory=list)
    team: str = ""
    minute: int = 0
    detail: str = ""


@dataclass
class WindowSnapshot:
    """Cumulative match stats observed at a given minute."""
    minute: int
    stats: dict[str, int] = field(default_factory=dict)

    def delta(self, earlier: "WindowSnapshot", field_name: str) -> int:
        return self.stats.get(field_name, 0) - earlier.stats.get(field_name, 0)
