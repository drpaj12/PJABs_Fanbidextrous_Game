# src/game/treasury.py
"""Gold awards: base party treasury, per-tile gold (deeper + Power = richer), gate loot,
and the second-half price multiplier."""
from src.utils.constants import CONFIG

_E = CONFIG["economy"]
_GBP = CONFIG["power"]["gold_bonus_per_power"]


def base_treasury(party_size: int) -> int:
    return int(_E["base_treasury_per_fighter"]) * int(party_size)


def _power_mult(power: int) -> float:
    return 1.0 + _GBP * power


def tile_gold(gates_passed: int, power: int) -> int:
    base = _E["gold_per_tile"] + _E["gold_depth_bonus_per_gate"] * gates_passed
    return int(round(base * _power_mult(power)))


def gate_loot_gold(power: int) -> int:
    return int(round(_E["gate_loot"] * _power_mult(power)))


def second_half_multiplier() -> float:
    return float(_E["second_half_price_multiplier"])
