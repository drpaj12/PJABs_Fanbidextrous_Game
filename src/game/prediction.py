# src/game/prediction.py
"""A single integer prediction for one stat in one window. Code form: stat:N."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Prediction:
    stat_code: str
    line: int

    def to_code(self) -> str:
        return f"{self.stat_code}:{self.line}"

    @classmethod
    def from_code(cls, code: str) -> "Prediction":
        if ":" not in code:
            raise ValueError(f"bad prediction code: {code!r}")
        stat, _, num = code.partition(":")
        if not stat or not num.lstrip("-").isdigit():
            raise ValueError(f"bad prediction code: {code!r}")
        return cls(stat_code=stat, line=int(num))
