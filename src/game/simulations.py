# src/game/simulations.py
"""Discover recorded simulation files (offline matches) for the game picker.

A simulation file is a recorded match consumed by ReplayFeed; each carries a `meta`
block (title / subtitle / home_team / away_team). This pure module scans the
simulations directory and returns a readable, deterministic (filename-sorted) list so
every offline mode can begin with a game list. No pygame, no rendering -- just the
filesystem and JSON, which keeps it unit-testable against a temp directory.
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimGame:
    """One recorded simulation: its repo-relative path plus display labels."""
    path: str            # repo-relative, e.g. "assets/data/simulations/x.json"
    title: str           # e.g. "France 4-2 Croatia"
    subtitle: str        # e.g. "2018 World Cup Final" (may be "")


def _meta_labels(meta: dict, stem: str) -> tuple[str, str]:
    """Derive (title, subtitle) from a sim's meta block, falling back to the filename."""
    title = str(meta.get("title") or "").strip()
    if not title:
        home = str(meta.get("home_team") or "").strip()
        away = str(meta.get("away_team") or "").strip()
        title = f"{home} v {away}".strip() if (home or away) else stem
    subtitle = str(meta.get("subtitle") or "").strip()
    return (title or stem), subtitle


def list_simulations(root: Path, sims_rel_dir: str) -> list[SimGame]:
    """Return every *.json simulation under root/sims_rel_dir, sorted by filename for a
    stable order. A file with no readable meta still appears (labelled by its filename),
    so a malformed sim is visible in the picker rather than silently dropped."""
    games: list[SimGame] = []
    base = root / sims_rel_dir
    if not base.is_dir():
        return games
    for fp in sorted(base.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as fh:
                meta = dict(json.load(fh).get("meta", {}))
        except (OSError, ValueError):
            meta = {}
        title, subtitle = _meta_labels(meta, fp.stem)
        games.append(SimGame(path=f"{sims_rel_dir}/{fp.name}",
                             title=title, subtitle=subtitle))
    return games
