# Live Fixture ID Resolution -- Design

**Date:** 2026-06-21
**Status:** IMPLEMENTED
**Supersedes:** `2026-06-20-real-fixture-id-harvest-design.md`

## Problem

The offline `assets/data/schedule.json` drives the picker, countdown, and draft using
synthetic ids (`2026NNN`) and real team names. The live data pipeline (lineups, statistics)
needs a REAL API-Football fixture id. The free tier blocks the season-filtered fixtures LIST
query (`fixtures?league=1&season=2026&date=...` -> "Free plans do not have access to this
season"), so we cannot look the id up by date. We do NOT want to pay, prefetch, or hand-curate
real ids.

## Key empirical findings (2026-06-21)

- `feed_cache.php?fixture=<real_id>&lead=1` returns FULL real 2026 World Cup lineups +
  statistics on the free key. Direct-by-id is not season-gated.
- `fixtures?live=all` is NOT season-gated and returns live 2026 World Cup matches with their
  real ids (observed: Spain v Saudi Arabia = 1489397, status 1H).
- Only the season-filtered LIST query is paywalled.

## Approach: resolve the real id at play time

When the player picks a game and the half begins, match the picked game's two team names to
whatever World Cup match is in play right now (`fixtures?live=all`, filtered to league 1) to
discover its real id. That id then drives the unchanged lineups -> statistics pipeline. No id
is prefetched, harvested, or stored on the client; it is resolved live, each time, only while
the match is actually being played.

A World Cup match only appears in `live=all` once it is IN PLAY (1H/2H), so before kickoff the
resolve screen shows the kickoff countdown and keeps polling -- which is exactly the intended
"resolve the game as it is played" behavior.

## Components

1. **`php/live_fixtures.php`** (new) -- lead-gated, single-shared-file cache (30s TTL) proxy
   of `fixtures?live=all`, filtered server-side to `league.id == 1`, projecting each match to
   `{id, home, away, status, elapsed}`. Same quota discipline as `feed_cache.php`: only the
   lead client (`?lead=1`) spends an upstream call; followers read the cache or get a
   `waiting_for_lead` marker. The key is read from `apifootball_key.txt` (server-side only).

2. **`src/game/live_resolver.py`** (new, pure, zero pygame) --
   `resolve_fixture_id(home, away, live_response) -> Optional[int]`. Normalizes names (NFKD
   accent-strip, lowercase, alphanumerics only) and applies a small alias map (Korea Republic
   == South Korea, Congo DR == DR Congo, IR Iran == Iran, Turkiye == Turkey, etc.). Matches
   when the two live-feed teams equal the picked pair as a set (home/away order irrelevant).
   A blank picked team or a same-team-twice pick never matches.

3. **`src/sync/feed_client.py`** (extended) -- `get_live_fixtures()` calls
   `live_fixtures.php`, lead-gated like `get_feed()`. New ctor param `live_fixtures_path`.

4. **`src/ui/screens/live_resolve_screen.py`** (new, all pygame) -- sits in front of the live
   flow. Polls `get_live_fixtures()` every `feed.live_resolve_poll_seconds` (lead polls
   immediately; followers offset by `follower_poll_delay_seconds`), runs `resolve_fixture_id`,
   and fires `on_resolved(real_id)` exactly once on a hit. Shows the kickoff countdown
   pre-kickoff, then "Connecting to live match...". SIM mode: tap to skip to `fallback_id`.
   Back button returns to the picker.

5. **`src/ui/flow.py`** (rewired) -- `start_live(...)` gains `home`/`away`. When both are
   present (the picker path), it shows `LiveResolveScreen` first; the rest of the live flow
   (warm cache, lineups wait, draft, windows) moved into an inner `run_with(real_id)` invoked
   by `on_resolved`. The `--live <real_id>` single-fixture path passes no home/away and skips
   resolution. `picked()` passes the picked game's `home`/`away`.

## Config

- `feed.live_resolve_poll_seconds = 30`
- `relay.live_fixtures_path = "/live_fixtures.php"`

## Quota

Free tier = 100 req/day. Resolution adds at most one shared upstream call per 30s cache window,
and only while the lead client sits on the resolve screen. Once resolved, the existing
`feed_cache.php` pipeline takes over.

## Testing

- `tests/test_live_resolver.py` -- exact match, order swap, accents, every alias, blank team,
  same-team-twice, string-id coercion, missing-id/non-dict entries, empty/None response.
- `TOOLS/smoke_flow.py::resolve_smoke` -- drives `LiveResolveScreen` headlessly with a fake
  transport: confirms `on_resolved` fires with the matched real id (alias + order-swap) and
  that a non-matching pick never resolves.

## Out of scope / left as-is

`php/fixtures.php` (the old harvest endpoint) remains deployed but unused. No real ids in
`schedule.json`. No paid plan.
