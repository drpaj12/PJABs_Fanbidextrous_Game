# tests/test_simulations.py
"""Tests for the recorded-simulation discovery used by the game picker."""
import json
from pathlib import Path

from src.game.simulations import SimGame, list_simulations


def _write(dir_path: Path, name: str, meta) -> None:
    payload = {"snapshots": []}
    if meta is not None:
        payload["meta"] = meta
    (dir_path / name).write_text(json.dumps(payload), encoding="utf-8")


def test_lists_sims_sorted_with_meta_labels(tmp_path: Path) -> None:
    sims = tmp_path / "sims"
    sims.mkdir()
    _write(sims, "b_game.json", {"title": "France 4-2 Croatia",
                                 "subtitle": "2018 World Cup Final"})
    _write(sims, "a_game.json", {"title": "Brazil 1-2 Belgium",
                                 "subtitle": "2018 World Cup Quarter-final"})

    games = list_simulations(tmp_path, "sims")

    assert [g.path for g in games] == ["sims/a_game.json", "sims/b_game.json"]
    assert games[0] == SimGame(path="sims/a_game.json", title="Brazil 1-2 Belgium",
                               subtitle="2018 World Cup Quarter-final")


def test_falls_back_to_home_away_then_filename(tmp_path: Path) -> None:
    sims = tmp_path / "sims"
    sims.mkdir()
    _write(sims, "teams_only.json", {"home_team": "Spain", "away_team": "Italy"})
    _write(sims, "no_meta.json", {})

    games = {g.path: g for g in list_simulations(tmp_path, "sims")}

    assert games["sims/teams_only.json"].title == "Spain v Italy"
    assert games["sims/no_meta.json"].title == "no_meta"   # filename stem fallback


def test_malformed_json_still_appears(tmp_path: Path) -> None:
    sims = tmp_path / "sims"
    sims.mkdir()
    (sims / "broken.json").write_text("{not valid json", encoding="utf-8")

    games = list_simulations(tmp_path, "sims")

    assert [g.path for g in games] == ["sims/broken.json"]
    assert games[0].title == "broken"


def test_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert list_simulations(tmp_path, "does_not_exist") == []
