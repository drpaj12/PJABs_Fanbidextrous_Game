# src/game/power.py
"""Power gained from a window's goal prediction. Persists for the rest of the crawl."""
from src.utils.constants import CONFIG

_P = CONFIG["power"]


def power_gain(predicted_line: int, actual: int) -> int:
    """Power for one goal prediction. A predicted line below min_predicted (e.g. 0) earns nothing,
    even when correct -- the safe pick grants no power."""
    if int(predicted_line) < _P["min_predicted"]:
        return 0
    diff = abs(int(predicted_line) - int(actual))
    if diff == 0:
        return int(_P["exact_gain"])
    if diff <= _P["close_max_diff"]:
        return int(_P["close_gain"])
    return 0
