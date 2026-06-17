#!/usr/bin/env python
# scripts/build_simulation_from_statsbomb.py
"""Generate offline simulation files from StatsBomb open data (FIFA World Cup 2018).

Fetches events + lineups for a handful of iconic matches, runs the pure adapter
(src/game/statsbomb_adapter), and writes one simulation JSON per match into
assets/data/simulations/. Run once; the generated files are committed so the game
needs no network at runtime.

Usage:  .venv/Scripts/python scripts/build_simulation_from_statsbomb.py

ASCII-only output. Player names are accent-folded by the adapter.
"""
import json
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from src.game.statsbomb_adapter import build_simulation, STAT_FIELDS  # noqa: E402

_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
_OUT_DIR = _ROOT / "assets" / "data" / "simulations"

# Iconic 2018 World Cup matches, all decided inside 90 minutes, varied stat profiles.
MATCHES = [
    {"id": 8658, "slug": "wc2018_final_fra_cro",
     "title": "France 4-2 Croatia", "subtitle": "2018 World Cup Final",
     "home_team": "France", "away_team": "Croatia", "final_score": [4, 2]},
    {"id": 8655, "slug": "wc2018_sf_fra_bel",
     "title": "France 1-0 Belgium", "subtitle": "2018 World Cup Semi-final",
     "home_team": "France", "away_team": "Belgium", "final_score": [1, 0]},
    {"id": 8650, "slug": "wc2018_qf_bra_bel",
     "title": "Brazil 1-2 Belgium", "subtitle": "2018 World Cup Quarter-final",
     "home_team": "Brazil", "away_team": "Belgium", "final_score": [1, 2]},
]


def _fetch(url: str) -> list:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for m in MATCHES:
        mid = m["id"]
        print(f"Fetching match {mid} ({m['title']}) ...")
        try:
            events = _fetch(f"{_BASE}/events/{mid}.json")
            lineups = _fetch(f"{_BASE}/lineups/{mid}.json")
        except Exception as exc:                                  # noqa: BLE001
            print(f"  FAIL fetch: {exc}")
            failures += 1
            continue

        meta = {k: m[k] for k in ("id", "title", "subtitle", "home_team", "away_team", "final_score")}
        sim = build_simulation(events, lineups, meta)

        final_stats = sim["snapshots"][-1]["stats"]
        goals = final_stats["goals"]
        expected = sum(m["final_score"])
        flag = "OK" if goals == expected else "MISMATCH"
        print(f"  goals={goals} expected={expected} [{flag}]  "
              + " ".join(f"{f}={final_stats[f]}" for f in STAT_FIELDS if f != "goals"))
        print(f"  starters in pool: {len(sim['lineups'])}  minutes: {len(sim['snapshots'])}")

        out_path = _OUT_DIR / f"{m['slug']}.json"
        with open(out_path, "w", encoding="ascii") as fh:
            json.dump(sim, fh, indent=1, ensure_ascii=True)
        print(f"  wrote {out_path.relative_to(_ROOT)}")
        if goals != expected:
            failures += 1

    print(f"\nDONE. {len(MATCHES) - failures}/{len(MATCHES)} matches OK.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
