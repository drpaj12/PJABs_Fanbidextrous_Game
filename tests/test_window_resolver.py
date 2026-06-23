# tests/test_window_resolver.py
from src.game.dungeon import DungeonState
from src.game.window_resolver import STAT_CODES, PartyGear, resolve_window


class SeqRng:
    def __init__(self, values):
        self._v = list(values)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i % len(self._v)]
        self._i += 1
        return v


def _exact_lines(goal):
    # progress stats all predicted to match the actuals below -> 4 * exact (3) = +12 tiles
    return {"goal": goal, "shot": 3, "corner": 2, "card": 1, "foul": 4}


ACTUALS = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}


def test_all_exact_one_fighter_advances_and_passes_gate():
    st = DungeonState(half=1, party_size=1)         # total 12, gate at 8
    gear = PartyGear(weapon_bonus=5, armor_soak=0, has_reroll=False, consumable_value=0)
    rng = SeqRng([6])                               # gate roll 6 + weapon 5 = 11 >= diff 6
    res = resolve_window(rng, st, gear, [_exact_lines(2)], ACTUALS, "W1 @15'")
    assert res.tiles_advanced == 12
    assert res.power_gained == 2                    # goal exact, predicted >= 1
    assert st.power == 2
    assert st.gates_passed == 1
    assert st.depth == 12 and st.finished is True   # reached total
    assert res.color == "green"
    assert any("PASS" in line for line in res.log)


def test_big_miss_forces_red_and_raises_threat():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=9, armor_soak=0)
    rng = SeqRng([6])
    lines = {"goal": 0, "shot": 99, "corner": 2, "card": 1, "foul": 4}   # shot big miss
    res = resolve_window(rng, st, gear, [lines], ACTUALS, "W1")
    assert res.color == "red"
    assert st.threat == 1
    assert res.power_gained == 0                    # predicted 0 goals -> no power


def test_stat_results_carry_per_prediction_outcomes_in_canonical_order():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=5, armor_soak=0)
    rng = SeqRng([6])
    # goal exact (2==2 -> green), shot big miss (99 vs 3 -> red), corner near (4 vs 2 -> orange)
    lines = {"goal": 2, "shot": 99, "corner": 4, "card": 1, "foul": 4}
    res = resolve_window(rng, st, gear, [lines], ACTUALS, "W1")
    assert [sr.code for sr in res.stat_results] == STAT_CODES
    by = {sr.code: sr for sr in res.stat_results}
    assert by["goal"].predicted == 2 and by["goal"].actual == 2 and by["goal"].color_key == "green"
    assert by["shot"].color_key == "red"            # big miss
    assert by["corner"].color_key == "orange"       # near/off, not exact, not big miss
    assert by["card"].color_key == "green" and by["foul"].color_key == "green"
    assert res.actuals == {c: ACTUALS[c] for c in STAT_CODES}


def test_resolve_emits_colored_prediction_log_lines():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=5, armor_soak=0)
    rng = SeqRng([6])
    res = resolve_window(rng, st, gear, [_exact_lines(2)], ACTUALS, "W1")
    pred_lines = [ln for ln in res.log if ln.strip().startswith("PRED")]
    assert len(pred_lines) == len(STAT_CODES)
    assert all("(GREEN)" in ln for ln in pred_lines)  # all exact
    # PRED lines sit between the advance line and the DEPTH progression line
    advance_i = next(i for i, ln in enumerate(res.log) if "party advance" in ln)
    depth_i = next(i for i, ln in enumerate(res.log) if ln.strip().startswith("DEPTH"))
    first_pred_i = next(i for i, ln in enumerate(res.log) if ln.strip().startswith("PRED"))
    assert advance_i < first_pred_i < depth_i


def test_gate_fail_costs_tiles_and_wound():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=0, armor_soak=0)
    rng = SeqRng([1])                               # roll 1 vs diff 6 -> fail, shortfall 5
    res = resolve_window(rng, st, gear, [_exact_lines(0)], ACTUALS, "W1")
    # advanced to gate (8) then lost 5 tiles -> depth 3, one wound
    assert st.wounds == 1 and st.depth == 3
    assert any("FAIL" in line for line in res.log)


# All-"off" predictions: diff 3-4 grades to the OFF band (step 0), so the party advances
# zero tiles -- slaying none of the engaged horde.
_OFF_LINES = {"goal": 0, "shot": 7, "corner": 5, "card": 5, "foul": 0}


def test_unslain_monsters_carry_into_threat():
    st = DungeonState(half=1, party_size=1)         # solo -> 1x6 = 6 goblins engaged
    gear = PartyGear(weapon_bonus=5, armor_soak=0)
    rng = SeqRng([6])
    res = resolve_window(rng, st, gear, [_OFF_LINES], ACTUALS, "W1")
    assert res.tiles_advanced == 0                  # nothing slain
    assert st.threat == 6                            # whole engaged horde carries over
    assert any("HORDE" in line and "unslain" in line for line in res.log)


def test_overkill_leaves_no_leftover_threat():
    st = DungeonState(half=1, party_size=1)         # 6 engaged, exact lines advance 12 tiles
    gear = PartyGear(weapon_bonus=5, armor_soak=0)
    rng = SeqRng([6])
    res = resolve_window(rng, st, gear, [_exact_lines(0)], ACTUALS, "W1")
    assert res.tiles_advanced == 12                 # >= 6 engaged
    assert st.threat == 0                            # none left behind
    assert not any("HORDE" in line for line in res.log)


def test_big_miss_threat_stacks_with_unslain_carry():
    st = DungeonState(half=1, party_size=1)         # 6 engaged
    gear = PartyGear(weapon_bonus=5, armor_soak=0)
    rng = SeqRng([6])
    # shot big miss (-1 tile, +1 threat), the other three progress stats OFF (0 tiles)
    lines = {"goal": 0, "shot": 99, "corner": 5, "card": 5, "foul": 0}
    res = resolve_window(rng, st, gear, [lines], ACTUALS, "W1")
    assert res.tiles_advanced == -1
    # +1 from the big miss, +6 from the unslain horde
    assert st.threat == 7
