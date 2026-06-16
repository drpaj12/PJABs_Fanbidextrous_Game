# tests/test_shot.py
import random
from src.game.athlete import DraftedAthlete
from src.game.shot import resolve_shot, pick_concede_attacker


def _ath(aid: str, arch: str, stars: int) -> DraftedAthlete:
    return DraftedAthlete(athlete_id=aid, name=aid, broad_position="Attacker",
                          team="T", jersey=1, archetype=arch, stars=stars)


def test_resolve_shot_is_deterministic_with_seeded_rng():
    rng = random.Random(42)
    ath = _ath("s", "ST", 5)  # conversion 0.50
    results = [resolve_shot(ath, rng, bonus=0.0) for _ in range(4)]
    rng2 = random.Random(42)
    results2 = [resolve_shot(ath, rng2, bonus=0.0) for _ in range(4)]
    assert results == results2


def test_bonus_can_force_certain_goal():
    rng = random.Random(1)
    ath = _ath("s", "GK", 1)  # low conversion
    assert resolve_shot(ath, rng, bonus=1.0) is True


def test_pick_concede_attacker_excludes_owned():
    pool = [_ath("p1", "ST", 3), _ath("p2", "WG", 3), _ath("p3", "CM", 3)]
    owned = {"p1", "p2"}
    rng = random.Random(0)
    chosen = pick_concede_attacker(pool, owned, rng)
    assert chosen.athlete_id == "p3"
