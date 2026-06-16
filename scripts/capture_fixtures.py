# scripts/capture_fixtures.py
"""Capture real API-Football JSON into tests/fixtures/ for deterministic tests.

Usage: API_FOOTBALL_KEY=... .venv/Scripts/python scripts/capture_fixtures.py <fixture_id>
ASCII output only.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://v3.football.api-sports.io"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key or len(sys.argv) < 2:
        print("FAIL: need API_FOOTBALL_KEY and a fixture id argument")
        return 1
    fid = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path in [("apifootball_lineups_real", f"/fixtures/lineups?fixture={fid}"),
                       ("apifootball_statistics_real", f"/fixtures/statistics?fixture={fid}")]:
        data = _get(path, key)
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=2))
        print(f"OK wrote {name}.json ({data.get('results', 0)} results)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
