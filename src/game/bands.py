# src/game/bands.py
"""Grade a progress-stat prediction into an accuracy band (tile step-points) and color a window."""
from dataclasses import dataclass

from src.utils.constants import CONFIG

_B = CONFIG["bands"]


@dataclass(frozen=True)
class Band:
    key: str
    step: int
    label: str
    is_big_miss: bool


def grade_progress(line: int, actual: int) -> Band:
    """Return the band for one progress stat by absolute error |line - actual|."""
    diff = abs(int(line) - int(actual))
    for key in _B["order"]:
        spec = _B[key]
        if diff <= spec["max_diff"]:
            return Band(key=key, step=int(spec["step"]), label=spec["label"],
                        is_big_miss=(key == "big_miss"))
    spec = _B["big_miss"]
    return Band(key="big_miss", step=int(spec["step"]), label=spec["label"], is_big_miss=True)


def window_color(tiles: int, has_big_miss: bool) -> str:
    """green for a strong window, red for a weak/failed one, orange otherwise."""
    wc = _B["window_color"]
    if has_big_miss or tiles <= wc["red_max"]:
        return "red"
    if tiles >= wc["green_min"]:
        return "green"
    return "orange"
