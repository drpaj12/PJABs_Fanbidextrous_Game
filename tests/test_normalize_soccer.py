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
