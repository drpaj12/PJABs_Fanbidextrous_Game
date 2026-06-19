# src/game/window_report.py
"""Plain-data summary of one resolved window, for the prediction screen's results panel.

Pure Python (no pygame): derives per-stat closeness/grade from the same `grade()` the
session uses, plus the meter fill percentages the window left behind. The UI reads this
to show the player how their last picks landed and how each fed the success/concede meters.
"""
from dataclasses import dataclass
from typing import Optional

from src.game.prediction import Prediction, grade
from src.game.session import ShotOutcome
from src.utils.constants import CONFIG

_S = CONFIG["scoring"]


@dataclass(frozen=True)
class StatResult:
    """One stat's outcome: the line you predicted vs what actually happened."""
    code: str
    label: str
    predicted: int
    actual: int
    diff: int
    outcome: str  # "exact" | "near" | "miss"
    success_credit: int
    concede_credit: int


@dataclass(frozen=True)
class WindowReport:
    """Everything the results panel shows about the window that just resolved."""
    window: int
    results: list[StatResult]
    success_value: int
    concede_value: int
    success_threshold: int
    concede_threshold: int
    success_pct: int
    concede_pct: int
    success_fired: bool
    concede_fired: bool
    success_shot: Optional[ShotOutcome] = None
    concede_shot: Optional[ShotOutcome] = None


def _outcome(diff: int) -> str:
    if diff == 0:
        return "exact"
    if diff <= _S["near_band"]:
        return "near"
    return "miss"


def _pct(value: int, threshold: int) -> int:
    if threshold <= 0:
        return 0
    return max(0, min(100, round(100 * value / threshold)))


def build_window_report(window: int, predictions: list[Prediction],
                        actuals: dict[str, int], stat_labels: dict[str, str],
                        success_value: int, concede_value: int,
                        success_threshold: int, concede_threshold: int,
                        success_fired: bool, concede_fired: bool,
                        success_shot: Optional[ShotOutcome] = None,
                        concede_shot: Optional[ShotOutcome] = None) -> WindowReport:
    """Assemble a WindowReport from the locked predictions and the resolved actuals.

    `success_value`/`concede_value` are the meter readings AFTER resolution (a fired
    meter has already reset to 0, which `success_fired`/`concede_fired` flag separately).
    `success_shot`/`concede_shot` carry the shot a fired meter earned (None if it did
    not fire).
    """
    results: list[StatResult] = []
    for p in predictions:
        actual = actuals.get(p.stat_code, 0)
        g = grade(p, actual)
        results.append(StatResult(
            code=p.stat_code,
            label=stat_labels.get(p.stat_code, p.stat_code),
            predicted=p.line,
            actual=actual,
            diff=abs(p.line - actual),
            outcome=_outcome(abs(p.line - actual)),
            success_credit=g.success_credit,
            concede_credit=g.concede_credit,
        ))
    return WindowReport(
        window=window,
        results=results,
        success_value=success_value,
        concede_value=concede_value,
        success_threshold=success_threshold,
        concede_threshold=concede_threshold,
        success_pct=_pct(success_value, success_threshold),
        concede_pct=_pct(concede_value, concede_threshold),
        success_fired=success_fired,
        concede_fired=concede_fired,
        success_shot=success_shot,
        concede_shot=concede_shot,
    )
