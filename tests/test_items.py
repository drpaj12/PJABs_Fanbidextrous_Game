# tests/test_items.py
from src.game.athlete import DraftedAthlete
from src.game.items import Item, build_catalog, build_item


def _ath(aid, name, pos):
    return DraftedAthlete.create(athlete_id=aid, name=name, broad_position=pos, team="X", jersey=9)


def test_position_maps_to_category_and_names_use_surname():
    w = build_item(_ath("a1", "Lionel Messi", "Attacker"), half=1, price_multiplier=1.0)
    assert w.category == "weapon" and w.two_handed is True and w.persist == "infinite"
    assert "Messi" in w.name
    c = build_item(_ath("m1", "Luka Modric", "Midfielder"), half=1, price_multiplier=1.0)
    assert c.category == "consumable" and c.persist == "round" and "Modric" in c.name


def test_price_scales_with_half_multiplier():
    a = _ath("a1", "Lionel Messi", "Attacker")
    base = build_item(a, half=1, price_multiplier=1.0).price
    h2 = build_item(a, half=2, price_multiplier=1.5).price
    assert h2 == round(base * 1.5)


def test_effect_value_and_deterministic_magic_option():
    gk = _ath("g1", "Manuel Neuer", "Goalkeeper")
    one = build_item(gk, 1, 1.0)
    two = build_item(gk, 1, 1.0)
    assert one.category == "magic" and one.effect["kind"] == "magic"
    assert one.effect["option"] == two.effect["option"]      # deterministic by athlete_id
    wpn = build_item(_ath("a2", "Kylian Mbappe", "Attacker"), 1, 1.0)
    assert wpn.effect["kind"] == "dice_bonus" and wpn.effect["value"] >= 1


def test_armor_has_a_slot_nonarmor_does_not():
    d = build_item(_ath("d1", "Paolo Maldini", "Defender"), half=1, price_multiplier=1.0)
    assert d.category == "armor"
    assert d.armor_slot in {"head", "body", "shield", "cloak"}
    w = build_item(_ath("a1", "Lionel Messi", "Attacker"), half=1, price_multiplier=1.0)
    assert w.armor_slot == ""


def test_armor_slot_is_deterministic_and_paired_with_name():
    a = _ath("d1", "Paolo Maldini", "Defender")
    one = build_item(a, 1, 1.0)
    two = build_item(a, 1, 1.0)
    assert one.armor_slot == two.armor_slot          # deterministic by athlete_id
    assert one.name == two.name


def test_build_catalog_one_item_per_athlete():
    pool = [_ath("a1", "Lionel Messi", "Attacker"), _ath("d1", "Paolo Maldini", "Defender")]
    cat = build_catalog(pool, half=1, price_multiplier=1.0)
    assert len(cat) == 2
    assert {i.category for i in cat} == {"weapon", "armor"}
