# src/game/scoring.py
"""Compact score-event codes that cross the relay, and shared-score aggregation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreEvent:
    slot: int       # 0 = player A, 1 = player B
    window: int
    side: str       # "for" or "against"
    scored: bool

    def to_code(self) -> str:
        return f"{self.slot}:{self.window}:{self.side}:{1 if self.scored else 0}"

    @classmethod
    def from_code(cls, code: str) -> "ScoreEvent":
        slot, window, side, scored = code.split(":")
        return cls(slot=int(slot), window=int(window), side=side, scored=scored == "1")


def aggregate(codes: list[str]) -> tuple[int, int]:
    """Return (shared_team_score, shared_opponent_score)."""
    team = opp = 0
    for code in codes:
        ev = ScoreEvent.from_code(code)
        if not ev.scored:
            continue
        if ev.side == "for":
            team += 1
        elif ev.side == "against":
            opp += 1
    return team, opp
