# tests/test_crawl.py
import random

import pytest

from src.game.athlete import DraftedAthlete
from src.game.crawl import CrawlSession
from src.game.treasury import base_treasury


def _pool():
    rows = [("sccr-1", "L. Messi", "Attacker"),    # -> weapon
            ("sccr-2", "V. van Dijk", "Defender"),  # -> armor
            ("sccr-3", "L. Modric", "Midfielder"),  # -> consumable
            ("sccr-4", "T. Courtois", "Goalkeeper")]  # -> magic
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="World", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _session(party_size=1):
    return CrawlSession(party_size=party_size, pool=_pool(), rng=random.Random(99))


def test_starts_with_base_treasury_and_one_loadout_per_fighter():
    s = _session(party_size=2)
    assert s.treasury == base_treasury(2)
    assert len(s.loadouts) == 2
    assert s.half == 1
    assert s.state.half == 1


def test_catalog_has_one_item_per_athlete_with_all_categories():
    s = _session()
    cats = {it.category for it in s.catalog()}
    assert cats == {"weapon", "armor", "consumable", "magic"}


def test_buy_deducts_gold_and_adds_to_loadout():
    s = _session()
    weapon = next(it for it in s.catalog() if it.category == "weapon")
    before = s.treasury
    ok, reason = s.buy(0, weapon)
    assert ok and reason == ""
    assert s.treasury == before - weapon.price
    assert s.loadouts[0].has_weapon()


def test_buy_refused_when_too_expensive():
    s = _session()
    s.treasury = 10
    weapon = next(it for it in s.catalog() if it.category == "weapon")
    ok, reason = s.buy(0, weapon)
    assert not ok and reason == "not enough gold"
    assert s.treasury == 10


def test_sell_refunds_full_price_and_removes_item():
    s = _session()
    armor = next(it for it in s.catalog() if it.category == "armor")
    s.buy(0, armor)
    mid = s.treasury
    s.sell(0, armor.item_id)
    assert s.treasury == mid + armor.price
    assert not any(it.item_id == armor.item_id for it in s.loadouts[0].items)


def test_resolve_window_advances_depth_logs_and_banks_gold():
    s = _session()
    lines = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}
    actuals = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}  # all EXACT
    before_gold = s.treasury
    result = s.resolve_window([lines], actuals, "H1 W1")
    assert s.state.depth > 0
    assert s.window_index == 1
    assert s.window_colors == [result.color]
    assert s.treasury >= before_gold  # tiles earn gold
    assert any("H1 W1" in line for line in s.log)


def test_unused_consumable_persists_in_inventory():
    """A potion sits in inventory until the player chooses to USE it -- resolving a window
    without deploying it must NOT drop it."""
    s = _session()
    cons = next(it for it in s.catalog() if it.category == "consumable")
    s.buy(0, cons)
    s.resolve_window([{"goal": 0, "shot": 0, "corner": 0, "card": 0, "foul": 0}], {}, "H1 W1")
    assert any(it.item_id == cons.item_id for it in s.loadouts[0].items)


def test_used_consumable_is_consumed_after_the_window():
    s = _session()
    cons = next(it for it in s.catalog() if it.category == "consumable")
    s.buy(0, cons)
    s.resolve_window([{"goal": 0, "shot": 0, "corner": 0, "card": 0, "foul": 0}], {},
                     "H1 W1", used_consumables=[[cons.item_id]])
    assert not any(it.item_id == cons.item_id for it in s.loadouts[0].items)


def test_party_gear_counts_only_used_consumables():
    s = _session()
    cons = next(it for it in s.catalog() if it.category == "consumable")
    s.buy(0, cons)
    assert s.party_gear().consumable_value == 0                       # not deployed
    assert s.party_gear([[cons.item_id]]).consumable_value == cons.effect["value"]


def test_begin_second_half_carries_power_resets_depth_and_window():
    s = _session()
    s.state.depth = 9
    s.state.power = 4
    s.window_index = 3
    s.begin_second_half()
    assert s.half == 2
    assert s.state.half == 2
    assert s.state.depth == 0
    assert s.state.power == 4          # Power persists across halves
    assert s.window_index == 0
    assert s.cleared_prev_halves == 9  # half-1 depth banked for the score


def test_percent_and_score_label_span_both_halves():
    s = _session()
    s.state.depth = 12        # full half-1 (12 tiles for party of 1)
    s.begin_second_half()
    s.state.depth = 8         # half of half-2 (16 tiles)
    assert s.cleared_total() == 20
    assert 0 < s.percent() < 100
    assert s.score_label().startswith("Depth 20/28")


def test_match_over_only_after_second_half_windows():
    s = _session()
    s.window_index = 3
    assert s.half_over() and not s.match_over()   # half 1 just ended
    s.begin_second_half()
    s.window_index = 3
    assert s.match_over()


def test_set_loadout_rebuilds_from_item_ids_without_charging_gold():
    import random
    from src.game.crawl import CrawlSession
    pool = _pool()
    session = CrawlSession(party_size=2, pool=pool, rng=random.Random(99))
    treasury_before = session.treasury
    catalog = session.catalog()
    weapon = next(it for it in catalog if it.category == "weapon")
    armor = next(it for it in catalog if it.category == "armor")
    notes = session.set_loadout(0, [weapon.item_id, armor.item_id])
    assert {it.item_id for it in session.loadouts[0].items} == {weapon.item_id, armor.item_id}
    assert session.treasury == treasury_before        # gold NOT touched
    assert notes == []
    # the SAME weapon can be given to another member (independent loadouts)
    session.set_loadout(1, [weapon.item_id])
    assert session.loadouts[1].items[0].item_id == weapon.item_id


def test_set_loadout_skips_unknown_items_with_a_note():
    import random
    from src.game.crawl import CrawlSession
    session = CrawlSession(party_size=1, pool=_pool(), rng=random.Random(1))
    notes = session.set_loadout(0, ["does-not-exist"])
    assert session.loadouts[0].items == []
    assert any("unknown" in n.lower() for n in notes)
