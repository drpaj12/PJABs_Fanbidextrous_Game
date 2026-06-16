# src/game/shot.py
"""Shot-attempt resolution. Local randomness; results are transmitted, not the rolls."""
import random
from src.game.athlete import DraftedAthlete
from src.game.powers import conversion_for


def resolve_shot(attacker: DraftedAthlete, rng: random.Random, bonus: float = 0.0) -> bool:
    """True if the shot scores. bonus is an additive conversion modifier (e.g. from a power)."""
    chance = conversion_for(attacker) + bonus
    return rng.random() < chance


def pick_concede_attacker(pool: list[DraftedAthlete], owned_ids: set[str],
                          rng: random.Random) -> DraftedAthlete:
    """Pick a threatening attacker from the pool, excluding the player's own athletes."""
    candidates = [a for a in pool if a.athlete_id not in owned_ids]
    if not candidates:
        candidates = list(pool)
    return candidates[rng.randrange(len(candidates))]
