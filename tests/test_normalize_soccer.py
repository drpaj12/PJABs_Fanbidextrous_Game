# tests/test_normalize_soccer.py
import json
from pathlib import Path
from src.game.normalize_soccer import parse_lineups, parse_statistics
from src.game.athlete import DraftedAthlete

FIX = Path(__file__).parent / "fixtures"


def test_parse_lineups_returns_drafted_athletes():
    data = json.loads((FIX / "apifootball_lineups_sample.json").read_text())
    athletes = parse_lineups(data)
    ids = {a.athlete_id for a in athletes}
    assert "sccr-501" in ids
    davies = next(a for a in athletes if a.athlete_id == "sccr-501")
    assert isinstance(davies, DraftedAthlete)
    assert davies.broad_position == "Defender"
    assert davies.team == "Canada"


def test_parse_statistics_to_stat_dict():
    data = json.loads((FIX / "apifootball_statistics_sample.json").read_text())
    stats = parse_statistics(data)
    assert stats["corner_kicks"] == 5
    assert stats["shots_on_goal"] == 4
    assert stats["goalkeeper_saves"] == 2


def test_actuals_from_raw_maps_api_fields_to_codes():
    from src.game.normalize_soccer import actuals_from_raw
    menu = {"stats": [
        {"code": "corner", "api_field": "corner_kicks"},
        {"code": "shot", "api_field": "shots_on_goal"},
        {"code": "goal", "api_field": "goals"},
    ]}
    raw = {"corner_kicks": 4, "shots_on_goal": 2}
    out = actuals_from_raw(raw, menu)
    assert out == {"corner": 4, "shot": 2, "goal": 0}  # missing field -> 0


def test_parse_statistics_sums_yellow_and_red_into_cards():
    from src.game.normalize_soccer import parse_statistics
    data = {"response": [{"statistics": [
        {"type": "Yellow Cards", "value": 2},
        {"type": "Red Cards", "value": 1},
    ]}]}
    assert parse_statistics(data)["cards"] == 3
