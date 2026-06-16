# tests/test_sport_event.py
from src.game.sport_event import SportEvent, WindowSnapshot


def test_sport_event_holds_athletes_and_type():
    ev = SportEvent(event_id="sccr-1", event_type="goal",
                    athlete_ids=["sccr-501"], team="CAN",
                    minute=34, detail="Normal Goal")
    assert ev.event_type == "goal"
    assert "sccr-501" in ev.athlete_ids


def test_window_snapshot_delta():
    start = WindowSnapshot(minute=0, stats={"corner_kicks": 2, "goals": 0})
    end = WindowSnapshot(minute=5, stats={"corner_kicks": 5, "goals": 1})
    assert end.delta(start, "corner_kicks") == 3
    assert end.delta(start, "goals") == 1
    assert end.delta(start, "missing_field") == 0
