# tests/test_prediction_grade.py
from src.game.prediction import Prediction, grade


def test_exact_gives_success_credit_2():
    g = grade(Prediction("corner", 3), actual=3)
    assert g.success_credit == 2 and g.concede_credit == 0


def test_off_by_one_gives_success_credit_1():
    g = grade(Prediction("corner", 3), actual=4)
    assert g.success_credit == 1 and g.concede_credit == 0
    g2 = grade(Prediction("corner", 3), actual=2)
    assert g2.success_credit == 1 and g2.concede_credit == 0


def test_off_by_more_than_one_gives_concede_2():
    g = grade(Prediction("corner", 3), actual=6)
    assert g.success_credit == 0 and g.concede_credit == 2
