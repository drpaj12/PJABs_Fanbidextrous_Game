# tests/test_stats_menu.py
"""Guard tests for assets/data/stats_menu.json shape and bridge to actuals_from_raw."""
import json
from pathlib import Path
from src.game.normalize_soccer import actuals_from_raw

_MENU = json.loads(
    (Path(__file__).resolve().parents[1] / "assets/data/stats_menu.json").read_text())


def test_menu_is_the_five_agreed_stats():
    codes = [s["code"] for s in _MENU["stats"]]
    assert codes == ["goal", "shot", "corner", "card", "foul"]
    assert "save" not in codes


def test_every_stat_has_required_keys():
    for s in _MENU["stats"]:
        for key in ("code", "label", "kind", "api_field", "default_line"):
            assert key in s, f"{s.get('code')} missing {key}"


def test_fouls_bridges_from_api_field_to_code():
    # raw is keyed by api_field (what parse_statistics produces); foul -> 7
    actuals = actuals_from_raw({"fouls": 7}, _MENU)
    assert actuals["foul"] == 7
