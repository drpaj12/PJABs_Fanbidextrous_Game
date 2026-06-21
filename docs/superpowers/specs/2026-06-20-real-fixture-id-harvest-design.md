# Real Fixture ID Harvest -- Design

**Date:** 2026-06-20
**Status:** Approved (pending probe confirmation)

## Problem

The live pipeline keys on `fixture_id` being a real API-Football id: `feed_cache.php`
queries `v3.football.api-sports.io/fixtures?id=<id>`, `/lineups?fixture=<id>`,
`/statistics?fixture=<id>`. The curated `assets/data/schedule.json` carries **synthetic**
ids (`2026NNN`), so picking a game + half makes the relay ask API-Football about a fixture
that does not exist -> empty lineups -> the wait screen hangs on "Waiting for team sheets".

## Goal

Make each picked game carry a **real** API-Football fixture id, resolved **once, ahead of
time** (ids are assigned when the schedule is published and never change). The live runtime
path is left untouched -- it keeps querying `?fixture=<id>`; we just make that id real.

## Decisions (locked)

- **ID source:** bake real ids into `schedule.json` via a one-time offline harvest (re-run
  only when match days are added). No pick-time lookup, no extra runtime quota.
- **Key access:** a new lead-gated, cached relay endpoint holds the key server-side; the
  harvester calls the relay, so the key never leaves the server or touches git.
- **Probe first:** confirm the key serves 2026 WC fixtures and capture exact team-name
  spellings before building the harvester + alias map.

## Components

### 1. `PHP_SCRIPTS/fixtures.php` (new relay endpoint)
Mirrors `feed_cache.php` discipline.
- `GET fixtures.php?date=YYYY-MM-DD&lead=1`
- `date` is a **UTC** calendar date (validated `^\d{4}-\d{2}-\d{2}$`).
- Cached per date in `fixtures_<date>.json`, TTL 6h (a day's fixture list is near-static).
- Fresh cache -> served to everyone, no upstream cost.
- Non-lead + stale/missing -> last cache, or `{"response":null,"waiting_for_lead":true}`.
- Lead only: `GET v3.football.api-sports.io/fixtures?league=1&season=2026&date=<date>`
  with `x-apisports-key` from `apifootball_key.txt`; persist + echo the raw response.
- Bounds harvest cost to one upstream call per distinct UTC date.

### 2. Probe (manual, after deploy)
One read-only call for a UTC date with games (`2026-06-20`: NED v SWE 17:00Z,
GER v CIV 20:00Z). Confirm `response[].fixture.id` present; record `teams.home.name` /
`teams.away.name` spellings for all teams seen. Drives the alias map below.

### 3. `TOOLS/fetch_fixture_ids.py` (offline harvester)
- Loads `assets/data/schedule.json`.
- Distinct query dates = the **UTC date prefix of each row's `kickoff_utc`** (NOT the local
  date -- e.g. ECU v CUW is "Sat Jun 20 8pm EDT" = `2026-06-21T00:00:00Z`, UTC date 06-21).
- For each date: `GET <relay>/fixtures.php?date=<utc-date>&lead=1`.
- Match each schedule row to a returned fixture by **UTC date + normalized team names**
  (alias map: e.g. Turkiye/Turkey, Congo DR/DR Congo, South Korea/Korea Republic,
  Ivory Coast/Cote d'Ivoire, Curacao; normalize accents + case). Stamp `fixture.id` into
  the row's `id`.
- Print every unmatched row (team names + date) for human review. Never guess silently.
- Writes `schedule.json` back (preserving field order + `_comment`). ASCII-only output.
- Idempotent: re-running with already-real ids is a no-op match.

### 4. Rebuild + repackage
After harvest: `build_web_mobile.py --build-only` -> mirror into `WEB_BUILD/PREDICTOR/`
-> `package_deploy.py`. Client then ships with real ids; live data flows on pick.

## Out of scope
- MLS / non-WC fixtures (separate league id/season; not in the WC harvest).
- Pick-time dynamic resolution (rejected in favor of ahead-of-time bake).
- Any change to `feed_cache.php` or the live runtime flow.

## Risks
- League id `1` / season `2026` assumption -- the probe verifies before harvest.
- Free-tier key may not serve 2026 WC fixtures -- the probe verifies.
- Team-name mismatch -> unmatched rows printed for manual id entry; not a silent failure.
