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


from src.utils.constants import CONFIG

_S = CONFIG["scoring"]


@dataclass(frozen=True)
class Grade:
    success_credit: int
    concede_credit: int


def grade(prediction: "Prediction", actual: int) -> Grade:
    diff = abs(prediction.line - actual)
    if diff == 0:
        return Grade(success_credit=_S["exact_credit"], concede_credit=0)
    if diff <= _S["near_band"]:
        return Grade(success_credit=_S["near_credit"], concede_credit=0)
    return Grade(success_credit=0, concede_credit=_S["miss_concede"])
