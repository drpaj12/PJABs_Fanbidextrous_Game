# tests/test_window_report.py
"""Window report is pure-data; no pygame here (golden rule)."""
from src.game.prediction import Prediction
from src.game.session import ShotOutcome
from src.game.window_report import build_window_report, StatResult, WindowReport


_LABELS = {"goal": "Goals", "corner": "Corners", "shot": "Shots on target"}


def _report(preds, actuals, **kw):
    defaults = dict(window=1, predictions=preds, actuals=actuals, stat_labels=_LABELS,
                    success_value=0, concede_value=0, success_threshold=6,
                    concede_threshold=6, success_fired=False, concede_fired=False)
    defaults.update(kw)
    return build_window_report(**defaults)


def test_exact_prediction_grades_success():
    r = _report([Prediction("goal", 2)], {"goal": 2})
    res = r.results[0]
    assert res.outcome == "exact"
    assert res.diff == 0
    assert res.success_credit == 2
    assert res.concede_credit == 0


def test_near_prediction_grades_near():
    r = _report([Prediction("corner", 3)], {"corner": 4})
    res = r.results[0]
    assert res.outcome == "near"
    assert res.diff == 1
    assert res.success_credit == 1
    assert res.concede_credit == 0


def test_miss_prediction_concedes():
    r = _report([Prediction("shot", 2)], {"shot": 9})
    res = r.results[0]
    assert res.outcome == "miss"
    assert res.success_credit == 0
    assert res.concede_credit == 2


def test_missing_actual_defaults_to_zero():
    r = _report([Prediction("goal", 0)], {})
    res = r.results[0]
    assert res.actual == 0
    assert res.outcome == "exact"


def test_label_falls_back_to_code():
    r = _report([Prediction("foul", 2)], {"foul": 2})
    assert r.results[0].label == "foul"


def test_meter_percentages_clamp_and_round():
    r = _report([], {}, success_value=3, concede_value=6,
                success_threshold=6, concede_threshold=6)
    assert r.success_pct == 50
    assert r.concede_pct == 100


def test_percentage_never_exceeds_100_or_drops_below_0():
    r = _report([], {}, success_value=99, concede_value=-5,
                success_threshold=6, concede_threshold=6)
    assert r.success_pct == 100
    assert r.concede_pct == 0


def test_zero_threshold_is_zero_percent():
    r = _report([], {}, success_value=4, success_threshold=0)
    assert r.success_pct == 0


def test_fired_flags_pass_through():
    r = _report([], {}, success_fired=True, concede_fired=True)
    assert r.success_fired is True
    assert r.concede_fired is True


def test_raw_meter_values_and_thresholds_are_carried():
    r = _report([], {}, success_value=4, concede_value=2,
                success_threshold=6, concede_threshold=5)
    assert (r.success_value, r.success_threshold) == (4, 6)
    assert (r.concede_value, r.concede_threshold) == (2, 5)


def test_shots_pass_through_when_provided():
    shot = ShotOutcome("A. Davies", "Striker", 0.64, True)
    r = _report([], {}, success_fired=True, success_shot=shot)
    assert r.success_shot is shot
    assert r.concede_shot is None


def test_shots_default_to_none():
    r = _report([Prediction("goal", 1)], {"goal": 1})
    assert r.success_shot is None
    assert r.concede_shot is None


def test_report_preserves_all_predictions_in_order():
    preds = [Prediction("goal", 1), Prediction("corner", 3), Prediction("shot", 2)]
    r = _report(preds, {"goal": 1, "corner": 3, "shot": 2})
    assert [res.code for res in r.results] == ["goal", "corner", "shot"]
    assert isinstance(r, WindowReport)
    assert all(isinstance(res, StatResult) for res in r.results)
