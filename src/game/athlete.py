# src/game/athlete.py
"""Drafted athlete + deterministic archetype/star derivation from athlete id."""
import hashlib
from dataclasses import dataclass
from src.utils.constants import CONFIG, load_data

_POWERS = load_data(CONFIG["assets"]["powers_file"])
_BUCKET_MAP: dict[str, list[str]] = _POWERS["broad_position_map"]
_MIN_STARS: int = CONFIG["rating"]["min_stars"]
_MAX_STARS: int = CONFIG["rating"]["max_stars"]


def _hash_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def derive_archetype(athlete_id: str, broad_position: str) -> str:
    options = _BUCKET_MAP.get(broad_position, _BUCKET_MAP["Midfielder"])
    return options[_hash_int("arch:" + athlete_id) % len(options)]


def derive_stars(athlete_id: str) -> int:
    span = _MAX_STARS - _MIN_STARS + 1
    return _MIN_STARS + (_hash_int("star:" + athlete_id) % span)


@dataclass
class DraftedAthlete:
    athlete_id: str
    name: str
    broad_position: str
    team: str
    jersey: int
    archetype: str
    stars: int

    @classmethod
    def create(cls, athlete_id: str, name: str, broad_position: str,
               team: str, jersey: int) -> "DraftedAthlete":
        return cls(
            athlete_id=athlete_id, name=name, broad_position=broad_position,
            team=team, jersey=jersey,
            archetype=derive_archetype(athlete_id, broad_position),
            stars=derive_stars(athlete_id),
        )
