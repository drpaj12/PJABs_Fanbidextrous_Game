# tests/test_loadout.py
from src.game.items import Item
from src.game.loadout import Loadout


def _item(iid, category, value=2, two_handed=False, option=None, price=100):
    effect = {"kind": "magic", "option": option} if category == "magic" else {"kind": "x", "value": value}
    return Item(item_id=iid, name=iid, category=category, price=price, two_handed=two_handed,
                persist="infinite", effect=effect, source_pos="X", stars=3)


def test_only_one_two_handed_weapon():
    lo = Loadout()
    lo.add(_item("w1", "weapon", two_handed=True))
    ok, reason = lo.can_add(_item("w2", "weapon", two_handed=True))
    assert ok is False and "weapon" in reason


def test_slot_cap_and_extra_slot_magic():
    lo = Loadout()
    for i in range(6):
        lo.add(_item(f"a{i}", "armor"))
    assert lo.can_add(_item("a6", "armor"))[0] is False         # cap 6 reached
    lo2 = Loadout()
    lo2.add(_item("ms", "magic", option="extra_slot"))           # raises cap to 7
    for i in range(6):
        lo2.add(_item(f"a{i}", "armor"))
    assert len(lo2.items) == 7


def test_best_bonuses_and_total_cost():
    lo = Loadout()
    lo.add(_item("w1", "weapon", value=3, two_handed=True, price=200))
    lo.add(_item("ar", "armor", value=2, price=90))
    lo.add(_item("mg", "magic", option="reroll", price=150))
    assert lo.best_weapon_bonus() == 3
    assert lo.best_armor_soak() == 2
    assert lo.has_reroll() is True
    assert lo.total_cost() == 440
