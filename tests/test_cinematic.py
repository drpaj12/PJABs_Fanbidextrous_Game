# tests/test_cinematic.py
"""Pure tests for the cinematic beat-script builder (no pygame)."""
from src.game.cinematic import (
    build_cinematic_script, Beat, CinematicScript,
    TICK, METER, EXPLODE, SHOT, GOAL, CONCEDE, MISS, SUMMARY,
)
from src.game.prediction import Prediction
from src.game.scoring import ScoreEvent

_LABELS = {"corner": "Corners", "shot": "Shots on target"}


def _kinds(script):
    return [b.kind for b in script.beats]


def test_hit_prediction_fills_success_meter_no_explode():
    # predict corners=3, actual=3 -> exact (success +2). before 0 -> after 2, no fire.
    script = build_cinematic_script(
        predictions=[Prediction("corner", 3)], actuals={"corner": 3},
        success_before=0, success_after=2, success_fired=False,
        concede_before=0, concede_after=0, concede_fired=False,
        threshold=6, score_events=[], stat_labels=_LABELS)
    assert TICK in _kinds(script)
    assert METER in _kinds(script)
    assert EXPLODE not in _kinds(script)
    assert script.team_delta == 0 and script.opp_delta == 0
    assert _kinds(script)[-1] == SUMMARY


def test_success_fire_inserts_explode_then_shot_then_goal():
    script = build_cinematic_script(
        predictions=[Prediction("corner", 3)], actuals={"corner": 3},
        success_before=4, success_after=0, success_fired=True,
        concede_before=0, concede_after=0, concede_fired=False,
        threshold=6, score_events=[ScoreEvent(0, 1, "for", True)],
        stat_labels=_LABELS)
    ks = _kinds(script)
    assert ks.index(EXPLODE) < ks.index(SHOT) < ks.index(GOAL)
    assert script.team_delta == 1


def test_success_fire_missed_shot_is_miss_not_goal():
    script = build_cinematic_script(
        predictions=[Prediction("corner", 3)], actuals={"corner": 3},
        success_before=4, success_after=0, success_fired=True,
        concede_before=0, concede_after=0, concede_fired=False,
        threshold=6, score_events=[ScoreEvent(0, 1, "for", False)],
        stat_labels=_LABELS)
    ks = _kinds(script)
    assert MISS in ks and GOAL not in ks
    assert script.team_delta == 0


def test_concede_fire_inserts_concede_beat():
    script = build_cinematic_script(
        predictions=[Prediction("shot", 2)], actuals={"shot": 9},
        success_before=0, success_after=0, success_fired=False,
        concede_before=4, concede_after=0, concede_fired=True,
        threshold=6, score_events=[ScoreEvent(0, 1, "against", True)],
        stat_labels=_LABELS)
    assert CONCEDE in _kinds(script)
    assert script.opp_delta == 1


def test_tick_carries_label_and_outcome():
    script = build_cinematic_script(
        predictions=[Prediction("corner", 3)], actuals={"corner": 9},
        success_before=0, success_after=0, success_fired=False,
        concede_before=0, concede_after=2, concede_fired=False,
        threshold=6, score_events=[], stat_labels=_LABELS)
    tick = next(b for b in script.beats if b.kind == TICK)
    assert tick.label == "Corners"
    assert tick.detail == "miss"          # diff 6 > near band


def test_summary_is_always_last_and_has_deltas():
    script = build_cinematic_script(
        predictions=[], actuals={}, success_before=0, success_after=0,
        success_fired=False, concede_before=0, concede_after=0,
        concede_fired=False, threshold=6, score_events=[], stat_labels={})
    assert script.beats[-1].kind == SUMMARY
