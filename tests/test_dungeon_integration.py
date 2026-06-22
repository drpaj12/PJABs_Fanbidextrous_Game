# tests/test_dungeon_integration.py
"""Play a full 3-window half through the pure engine: build a catalog from a demo lineup,
equip a fighter, resolve three windows, and assert the party descends and scores a percent."""
import random

from src.game.athlete import DraftedAthlete
from src.game.dungeon import DungeonState
from src.game.items import build_catalog
from src.game.loadout import Loadout
from src.game.score import percent_complete
from src.game.treasury import base_treasury
from src.game.window_resolver import PartyGear, resolve_window


def _pool():
    specs = [("a1", "Lionel Messi", "Attacker"), ("d1", "Paolo Maldini", "Defender"),
             ("m1", "Luka Modric", "Midfielder"), ("g1", "Manuel Neuer", "Goalkeeper")]
    return [DraftedAthlete.create(athlete_id=a, name=n, broad_position=p, team="X", jersey=9)
            for a, n, p in specs]


def _gear_from(loadout: Loadout) -> PartyGear:
    return PartyGear(weapon_bonus=loadout.best_weapon_bonus(),
                     armor_soak=loadout.best_armor_soak(),
                     has_reroll=loadout.has_reroll())


def test_full_half_descent_and_score():
    party_size = 1
    treasury = base_treasury(party_size)
    assert treasury == 300

    catalog = build_catalog(_pool(), half=1, price_multiplier=1.0)
    weapon = next(i for i in catalog if i.category == "weapon")
    armor = next(i for i in catalog if i.category == "armor")
    loadout = Loadout()
    # A fighter cannot fully kit out on the base treasury; buy the weapon (it drives
    # gate-passing) and only add armor if it still fits the budget.
    loadout.add(weapon)
    if loadout.total_cost() + armor.price <= treasury:
        loadout.add(armor)
    treasury -= loadout.total_cost()
    assert treasury >= 0

    state = DungeonState(half=1, party_size=party_size)
    rng = random.Random(99)                      # deterministic
    actuals = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}
    good = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}   # all exact

    total_gold = 0
    for w in range(1, 4):
        gear = _gear_from(loadout)
        res = resolve_window(rng, state, gear, [good], actuals, f"W{w}")
        total_gold += res.gold
        if state.finished:
            break

    assert state.depth > 0
    assert state.depth <= state.total_tiles
    assert total_gold > 0
    pct = percent_complete(state.depth, party_size)
    assert 0 < pct <= 100


def test_party_size_scaling_keeps_completion_comparable():
    # A 3-fighter party advances ~3x faster through a ~3x-longer dungeon, so the same per-fighter
    # quality of play yields a comparable percent.
    from src.game.score import total_tiles_half
    assert total_tiles_half(1, 3) == 3 * total_tiles_half(1, 1)
