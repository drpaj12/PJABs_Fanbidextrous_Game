# tests/test_treasury.py
from src.game.treasury import base_treasury, gate_loot_gold, second_half_multiplier, tile_gold


def test_base_treasury_scales_with_party():
    assert base_treasury(1) == 300
    assert base_treasury(3) == 900


def test_tile_gold_grows_with_gates_and_power():
    assert tile_gold(gates_passed=0, power=0) == 5
    assert tile_gold(gates_passed=1, power=0) == 8          # 5 + 3
    assert tile_gold(gates_passed=0, power=10) == 10        # 5 * (1 + 0.10*10) = 10


def test_gate_loot_and_multiplier():
    assert gate_loot_gold(power=0) == 50
    assert gate_loot_gold(power=10) == 100                  # 50 * 2
    assert second_half_multiplier() == 1.5
