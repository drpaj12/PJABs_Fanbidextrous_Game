# tests/test_dungeon.py
from src.game.dungeon import (DungeonState, gate_step, monster_difficulty,
                              monster_flavor, resolve_gate)


class SeqRng:
    """Deterministic stand-in for random.Random: returns queued randint values in order."""
    def __init__(self, values):
        self._v = list(values)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i % len(self._v)]
        self._i += 1
        return v


def test_state_total_tiles_and_helpers():
    st = DungeonState(half=1, party_size=3)
    assert st.total_tiles == 36
    assert gate_step(1) == 8 and gate_step(2) == 6
    assert monster_difficulty(1, 3, 0) == 8        # 6 + 1*(3-1)
    assert monster_difficulty(1, 1, 2) == 8        # 6 + 0 + 1*2 threat


def test_monster_flavor_matches_difficulty_and_party_split():
    f = monster_flavor(half=1, party_size=3, threat=0)
    assert f["total"] == monster_difficulty(1, 3, 0)          # 8
    assert f["yours"] == max(1, round(f["total"] / 3))         # round(8/3) = 3
    assert f["name"] == "goblins"
    assert f["text"] == "Your party is engaging 8 goblins, you will fight 3 of them."


def test_monster_flavor_half2_name_and_solo_floor():
    f = monster_flavor(half=2, party_size=1, threat=0)
    assert f["name"] == "ogres"
    assert f["total"] == monster_difficulty(2, 1, 0)
    assert f["yours"] == f["total"]                            # solo fights them all
    # yours never drops below 1 even if total/party rounds down toward zero
    assert monster_flavor(half=1, party_size=99, threat=0)["yours"] >= 1


def test_gate_pass_with_weapon_and_power():
    rng = SeqRng([3])                               # base roll 3
    out = resolve_gate(rng, weapon_bonus=4, armor_soak=0, power=1, half=1,
                       party_size=1, threat=0)      # diff 6; 3+4+1 = 8 >= 6
    assert out.passed is True and out.roll == 8 and out.difficulty == 6


def test_gate_fail_soak_reduces_tiles_lost():
    rng = SeqRng([1])                               # base roll 1
    out = resolve_gate(rng, weapon_bonus=0, armor_soak=2, power=0, half=1,
                       party_size=1, threat=0)      # diff 6; roll 1; shortfall 5; soak 2
    assert out.passed is False and out.soaked == 2 and out.tiles_lost == 3 and out.wound is True


def test_reroll_takes_second_die_on_fail():
    rng = SeqRng([1, 6])                            # first roll fails, reroll = 6
    out = resolve_gate(rng, weapon_bonus=0, armor_soak=0, power=0, half=1,
                       party_size=1, threat=0, reroll=True)   # diff 6; reroll 6 >= 6
    assert out.passed is True and out.roll == 6


def test_dungeon_state_round_trips_through_dict():
    st = DungeonState(half=2, party_size=3, depth=11, power=4, wounds=1,
                      threat=2, gates_passed=2, finished=False)
    again = DungeonState.from_dict(st.to_dict())
    assert again.to_dict() == st.to_dict()
    assert again.total_tiles == st.total_tiles
