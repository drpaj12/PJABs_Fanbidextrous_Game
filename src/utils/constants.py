"""
constants.py -- loads config/game_config.json once and exposes it as CONFIG.

Every module that needs a constant imports from here:
    from src.utils.constants import CONFIG
    width = CONFIG["display"]["width"]

Data files (powers, stats menu) load via load_data:
    from src.utils.constants import CONFIG, load_data
    powers = load_data(CONFIG["assets"]["powers_file"])

Never import values directly from JSON elsewhere.
Never hardcode numbers in game or UI modules.
"""

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
ROOT: Path = _ROOT   # repo root; used to resolve data dirs (e.g. the simulations picker)


def _load_json(rel_path: str) -> dict[str, Any]:
    with open(_ROOT / rel_path, encoding="utf-8") as fh:
        return json.load(fh)


CONFIG: dict[str, Any] = _load_json("config/game_config.json")


def load_data(rel_path: str) -> dict[str, Any]:
    """Load a JSON data file by repo-relative path (e.g. assets/data/powers.json)."""
    return _load_json(rel_path)


class Layout:
    """Named UI geometry values with defaults. Loaded once. No magic numbers in UI."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def param(self, key: str, default: Any = 0) -> Any:
        return self._data.get(key, default)

    def i(self, key: str, default: int = 0) -> int:
        return int(self._data.get(key, default))

    def f(self, key: str, default: float = 0.0) -> float:
        return float(self._data.get(key, default))


LAYOUT: Layout = Layout(_load_json("config/layout_config.json"))
