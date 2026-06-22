# tests/test_power.py
from src.game.power import power_gain


def test_predicting_zero_never_grants_power():
    assert power_gain(0, 0) == 0
    assert power_gain(0, 5) == 0


def test_exact_and_close_bands():
    assert power_gain(2, 2) == 2   # exact, predicted >= 1
    assert power_gain(2, 3) == 1   # close (diff 1)
    assert power_gain(2, 1) == 1   # close (diff 1)


def test_far_goal_prediction_grants_nothing():
    assert power_gain(2, 5) == 0
