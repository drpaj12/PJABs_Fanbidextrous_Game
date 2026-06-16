"""
constants.py -- loads config/game_config.json once and exposes it as CONFIG.

Every module that needs a constant imports from here:
    from src.utils.constants import CONFIG
    width = CONFIG["display"]["width"]

Never import values directly from JSON elsewhere.
Never hardcode numbers in game or UI modules.
"""

import json
import os

_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "game_config.json",
)

with open(_config_path, "r", encoding="utf-8") as _f:
    CONFIG: dict = json.load(_f)
