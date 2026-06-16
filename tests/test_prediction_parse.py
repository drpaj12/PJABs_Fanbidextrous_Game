# tests/test_prediction_parse.py
import pytest
from src.game.prediction import Prediction


def test_round_trip_code():
    p = Prediction(stat_code="corner", line=3)
    assert p.to_code() == "corner:3"
    assert Prediction.from_code("corner:3") == p


def test_from_code_rejects_garbage():
    with pytest.raises(ValueError):
        Prediction.from_code("nonsense")
