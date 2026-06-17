# Remaining Work

Status as of 2026-06-16: Plan v1 is complete. The game is a working **single-device
mock demo** (full draft -> predict -> resolve -> reveal -> final loop), 41 tests pass,
the engine is pygame-free, and the pygbag mobile bundle builds. The network layer
(PHP relay + RelayClient + FeedClient) and the live-feed normalizer are **built and
tested but not yet wired into gameplay**.

This file tracks everything still open. Checkbox syntax (`- [ ]` / `- [x]`) so it can
be picked up by subagent-driven-development.

---

## A. Manual gates (need a human + live resources -- cannot be automated here)

- [ ] **A1. API-Football live smoke test.** Run `scripts/smoke_test_apifootball.py`
  with a real key during an actual live match. This is the gate that confirms the live
  JSON shape before anyone wires the feed into the watch loop. Put the key in
  `php/apifootball_key.txt` (server-side, never in the build).
- [ ] **A2. In-browser pygbag smoke test.** Open the built mobile bundle
  (`WEB_BUILD/game_web_mobile.zip` output) on a phone-sized viewport and confirm it
  renders and plays. The build succeeds; it has not yet been loaded in a browser.

---

## B. Simulated events from real World Cup data (NEW -- see data-source note below)

Goal: drive the game off a recorded real match timeline (replayed minute-by-minute as
if live) so the full loop can be exercised and tuned without waiting for a live fixture.

- [ ] **B1. Decide the data source** (see "World Cup events data" section below).
  Default recommendation: try API-Football historical first (zero new schema work);
  fall back to StatsBomb open data (free, unlimited, but needs an adapter).
- [ ] **B2. Capture one or two full World Cup matches** into `tests/fixtures/`
  (events + lineups + statistics if API-Football; or raw StatsBomb event JSON).
  Reuse / extend `scripts/capture_fixtures.py`.
- [ ] **B3. Build a `ReplayFeed`** (same interface as `MockFeed`: `snapshot_at(minute)`)
  that steps through the captured timeline, accumulating per-stat counts up to each
  minute. Pure Python, lives in `src/game/`, fully unit-tested.
- [ ] **B4. (Only if StatsBomb)** write a thin StatsBomb-event -> engine-stat adapter
  (map StatsBomb event types to corner / shot / save / goal / card counts). The engine
  is already sport-agnostic, so this is an isolated adapter, not an engine change.
- [ ] **B5. Add a "replay demo" entry path** alongside the existing mock demo so the
  game can be played start-to-finish against a real recorded match.

---

## C. Deferred follow-up plan (real remaining feature work)

This is the actual point of the game and deserves its own brainstorm -> plan -> execute
cycle. All the plumbing already exists and passes tests; what is missing is the wiring.

- [ ] **C1. Live two-player loop.** Join screen (session code + seed exchange), POST
  drafts/picks to the relay, poll the opponent's picks and score events, reconcile two
  `GameSession`s into the shared score. (Relay `php/soccer_api.php` + `RelayClient` are
  built and tested; the UI wiring is what remains.)
- [ ] **C2. Live feed into the watch loop.** Connect
  `feed_cache.php -> FeedClient -> normalize_soccer` into gameplay. Depends on A1.
  Includes the two documented live-path deferrals:
    - `goal` sourcing -- goals are NOT in the statistics endpoint; they come from the
      fixture/events endpoint. `actuals_from_raw` currently resolves `goal` to 0 on the
      live path until this is wired.
    - `events_between` incident counting (currently returns `[]`).
- [ ] **C3. Opponent-mode UI.** Virtual vs. real home/away, and the real-scoreline
  comparison at full time.
- [ ] **C4. Polish.** Audio, art, and error states (no match today, API down, relay
  unreachable, opponent pick timeout).
- [ ] **C5. NHL adapter.** Engine is already generic; only a new adapter is needed.

---

## World Cup events data -- can we use it for simulated events? (B1 research)

Short answer: **yes, two good options.**

### Option 1: API-Football historical (lowest friction -- reuses existing code)
- API-Football covers the World Cup (league id `1`) with historical fixtures, events,
  lineups, and statistics. Our `normalize_soccer` already targets this exact JSON shape,
  so a captured WC match drops straight into the existing pipeline with no schema work.
- VAR events exist from the 2020-2021 season onward.
- **Caveat:** the FREE plan restricts which seasons are available (recent seasons only,
  ~100 requests/day). Whether the free key exposes a World Cup season (e.g. 2022) must
  be verified with the actual key -- this is part of gate A1 / task B1. If the free tier
  does not expose a WC season, use Option 2.
- Action: one `capture_fixtures.py` run against `league=1` with a candidate season to
  see what the free key returns.

### Option 2: StatsBomb Open Data (free, unlimited, no key -- but needs an adapter)
- `https://github.com/statsbomb/open-data` -- free JSON, no API key, no rate limit.
  Includes the full **FIFA World Cup 2018** (men's) and the Women's World Cup, with
  rich event-level data (every pass, shot, card, goal, substitution) plus lineups.
- Layout: `data/competitions.json` lists competitions/seasons; `data/matches/<comp>/<season>.json`
  lists matches; `data/events/<match_id>.json` is the minute-by-minute event timeline;
  `data/lineups/<match_id>.json` the lineups. Schema docs live in the repo's `doc/` dir.
- This is ideal for a deterministic replay timeline, but its schema is StatsBomb's own
  (not API-Football), so it needs the thin adapter in task B4.

### Recommendation
Try Option 1 first (it is nearly free wiring given the existing normalizer). If the free
API-Football key will not surface a World Cup season, switch to Option 2 -- StatsBomb is
fully free and unlimited and the adapter is small because the engine is sport-agnostic.

Sources:
- StatsBomb Open Data: https://github.com/statsbomb/open-data
- API-Football v3 docs: https://www.api-football.com/documentation-v3
