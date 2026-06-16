# src/game/powers.py
"""Power resolution: load the data table, scale effects by star rating."""
from src.utils.constants import CONFIG, load_data
from src.game.athlete import DraftedAthlete

_POWERS = load_data(CONFIG["assets"]["powers_file"])
_ARCH = _POWERS["archetypes"]
_R = CONFIG["rating"]


def scaled_magnitude(base: float, stars: int) -> float:
    return base * (_R["mag_floor"] + _R["mag_per_star"] * stars)


def conversion_for(athlete: DraftedAthlete) -> float:
    base = _ARCH[athlete.archetype]["conversion_base"]
    return base + _R["conv_per_star"] * athlete.stars


def _effect(athlete: DraftedAthlete, slot: str) -> dict:
    raw = _ARCH[athlete.archetype][slot]
    return {"kind": raw["kind"], "value": scaled_magnitude(raw["value"], athlete.stars)}


def this_window_effect(athlete: DraftedAthlete) -> dict:
    return _effect(athlete, "this_window")


def next_window_effect(athlete: DraftedAthlete) -> dict:
    return _effect(athlete, "next_window")
