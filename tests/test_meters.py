# tests/test_meters.py
from src.game.meters import Meter


def test_add_below_threshold_does_not_fire():
    m = Meter(threshold=6)
    assert m.add(4) is False
    assert m.value == 4


def test_add_reaching_threshold_fires_and_resets():
    m = Meter(threshold=6)
    assert m.add(6) is True
    assert m.value == 0


def test_negative_credit_floors_at_zero():
    m = Meter(threshold=6)
    m.add(1)
    m.add(-5)
    assert m.value == 0
