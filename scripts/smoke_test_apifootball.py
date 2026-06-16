# scripts/smoke_test_apifootball.py
"""Manual smoke test: confirm API-Football free tier serves live fixtures + lineups + stats.

Usage:
  set API_FOOTBALL_KEY in env, then:
  .venv/Scripts/python scripts/smoke_test_apifootball.py
ASCII output only.
"""
import json
import os
import sys
import urllib.request

BASE = "https://v3.football.api-sports.io"


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        print("FAIL: set API_FOOTBALL_KEY in the environment first")
        return 1

    print("=== API-Football free-tier smoke test ===")
    live = _get("/fixtures?live=all", key)
    errors = live.get("errors")
    if errors:
        print("API errors:", errors)
    count = live.get("results", 0)
    print(f"live fixtures returned: {count}")
    if not count:
        print("NOTE: no live matches right now OR free tier blocks current season.")
        print("Re-run during a live match to disambiguate.")
        return 2

    fixture = live["response"][0]
    fid = fixture["fixture"]["id"]
    print(f"sample fixture id: {fid}")

    lineups = _get(f"/fixtures/lineups?fixture={fid}", key)
    print(f"lineups results: {lineups.get('results', 0)} (errors: {lineups.get('errors')})")

    stats = _get(f"/fixtures/statistics?fixture={fid}", key)
    print(f"statistics results: {stats.get('results', 0)} (errors: {stats.get('errors')})")

    ok = lineups.get("results", 0) and stats.get("results", 0)
    print("RESULT:", "OK - free tier serves live lineups + stats" if ok
          else "FAIL - lineups or stats unavailable on free tier")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
