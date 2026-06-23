# src/game/dungeon.py
"""Linear dungeon depth track: party state, gate spacing, monster difficulty, and a single
seeded gate dice resolution. All randomness comes from the injected rng (random.Random)."""
import random
from dataclasses import dataclass

from src.game.score import total_tiles_half
from src.utils.constants import CONFIG

_D = CONFIG["dungeon"]
_ROLL_BONUS_PER_POWER = int(CONFIG["power"]["roll_bonus_per_power"])


@dataclass
class DungeonState:
    half: int
    party_size: int
    depth: int = 0
    power: int = 0
    wounds: int = 0
    threat: int = 0
    gates_passed: int = 0
    finished: bool = False

    @property
    def total_tiles(self) -> int:
        return total_tiles_half(self.half, self.party_size)

    def to_dict(self) -> dict:
        return {
            "half": self.half,
            "party_size": self.party_size,
            "depth": self.depth,
            "power": self.power,
            "wounds": self.wounds,
            "threat": self.threat,
            "gates_passed": self.gates_passed,
            "finished": self.finished,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DungeonState":
        return cls(
            half=int(d["half"]),
            party_size=int(d["party_size"]),
            depth=int(d.get("depth", 0)),
            power=int(d.get("power", 0)),
            wounds=int(d.get("wounds", 0)),
            threat=int(d.get("threat", 0)),
            gates_passed=int(d.get("gates_passed", 0)),
            finished=bool(d.get("finished", False)),
        )


def gate_step(half: int) -> int:
    return int(_D["gate_every_tiles_half1"] if half == 1 else _D["gate_every_tiles_half2"])


def monster_difficulty(half: int, party_size: int, threat: int) -> int:
    base = _D["monster_base_difficulty_half1"] if half == 1 else _D["monster_base_difficulty_half2"]
    return int(base
               + _D["monster_difficulty_per_fighter"] * (party_size - 1)
               + _D["monster_difficulty_per_threat"] * threat)


@dataclass(frozen=True)
class GateOutcome:
    passed: bool
    roll: int
    difficulty: int
    soaked: int
    tiles_lost: int
    wound: bool


def resolve_gate(rng: random.Random, weapon_bonus: int, armor_soak: int, power: int, half: int,
                 party_size: int, threat: int, consumable_value: int = 0,
                 reroll: bool = False) -> GateOutcome:
    """Roll d(dice_sides) + weapon + Power*roll_bonus + consumable vs monster difficulty.
    On a failed roll, reroll (if available) once, then armor soaks the shortfall; any leftover
    costs tiles and inflicts a wound."""
    diff = monster_difficulty(half, party_size, threat)
    sides = int(_D["dice_sides"])
    bonus = weapon_bonus + _ROLL_BONUS_PER_POWER * power + consumable_value
    roll = rng.randint(1, sides) + bonus
    if roll < diff and reroll:
        roll = rng.randint(1, sides) + bonus
    if roll >= diff:
        return GateOutcome(True, roll, diff, 0, 0, False)
    shortfall = diff - roll
    soaked = min(armor_soak, shortfall)
    tiles_lost = (shortfall - soaked) * int(_D["tiles_lost_per_unsoaked_point"])
    return GateOutcome(False, roll, diff, soaked, tiles_lost, True)
