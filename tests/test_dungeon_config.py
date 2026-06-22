# tests/test_dungeon_config.py
"""Config-shape guards for the dungeon redesign."""
from src.utils.constants import CONFIG, load_data


def test_window_timing_is_fifteen_minutes():
    g = CONFIG["game"]
    assert g["window_seconds"] == 900
    assert g["windows_per_half"] == 3
    assert g["half_minutes"] * 60 // g["window_seconds"] == g["windows_per_half"]
    assert g["loadout_size"] == 6


def test_band_blocks_present_and_ordered():
    b = CONFIG["bands"]
    assert b["order"] == ["exact", "close", "near", "off", "big_miss"]
    assert b["exact"]["step"] == 3 and b["big_miss"]["step"] == -1
    assert b["window_color"]["green_min"] == 8 and b["window_color"]["red_max"] == 2


def test_power_dungeon_economy_blocks_present():
    assert CONFIG["power"]["min_predicted"] == 1
    assert CONFIG["dungeon"]["dice_sides"] == 6
    assert CONFIG["dungeon"]["max_wounds"] == 3
    assert CONFIG["economy"]["base_treasury_per_fighter"] == 300


def test_item_templates_cover_every_category():
    t = load_data("assets/data/item_templates.json")
    for cat in ("weapon", "armor", "consumable", "magic"):
        assert t[cat]["names"], cat
    assert t["weapon"]["two_handed"] is True
    assert t["magic"]["effect"]["options"]
