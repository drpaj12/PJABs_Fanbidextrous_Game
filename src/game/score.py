# src/game/score.py
"""Dungeon tile totals (party-size scaled) and the party's percent-completed score."""
from src.utils.constants import CONFIG

_D = CONFIG["dungeon"]


def total_tiles_half(half: int, party_size: int) -> int:
    key = "tiles_per_fighter_half1" if half == 1 else "tiles_per_fighter_half2"
    return int(_D[key]) * int(party_size)


def total_tiles_game(party_size: int) -> int:
    return total_tiles_half(1, party_size) + total_tiles_half(2, party_size)


def percent_complete(depth_done: int, party_size: int) -> int:
    """depth_done = cumulative tiles cleared across both halves. Returns 0..100."""
    total = total_tiles_game(party_size)
    if total <= 0:
        return 0
    return round(100 * min(int(depth_done), total) / total)
