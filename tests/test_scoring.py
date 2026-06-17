# tests/test_scoring.py
from src.game.scoring import ScoreEvent, aggregate


def test_score_event_round_trip():
    ev = ScoreEvent(slot=0, window=3, side="for", scored=True)
    assert ScoreEvent.from_code(ev.to_code()) == ev


def test_aggregate_counts_only_scored_goals():
    codes = [
        ScoreEvent(0, 1, "for", True).to_code(),
        ScoreEvent(1, 1, "for", False).to_code(),   # missed, no goal
        ScoreEvent(1, 2, "for", True).to_code(),
        ScoreEvent(0, 2, "against", True).to_code(),
    ]
    team, opp = aggregate(codes)
    assert team == 2
    assert opp == 1


def test_score_event_from_code_rejects_malformed():
    import pytest
    from src.game.scoring import ScoreEvent
    with pytest.raises(ValueError):
        ScoreEvent.from_code("0:1:for")  # only 3 parts


def test_score_event_code_roundtrip():
    from src.game.scoring import ScoreEvent
    ev = ScoreEvent(slot=0, window=2, side="against", scored=True)
    assert ScoreEvent.from_code(ev.to_code()) == ev
