# Live Single-Player Build (Scotland vs Morocco) -- Design

**Date:** 2026-06-19
**Status:** Approved (design); pending spec review
**Match:** Scotland vs Morocco, 2026 FIFA World Cup group stage, 18:00 ET, Gillette Stadium

## Goal

Let one player play the existing half-game against a **real, in-progress match**, with
lineups and stats pulled live from API-Football through the existing PHP relay, instead
of a canned `ReplayFeed`. The number of scored windows is whatever is **left in the first
half** when the player starts; the game advances in **real wall-clock time** with the live
match.

## Scope

**In (increment 1):**
- A `LiveFeed` (sibling of `ReplayFeed`) implementing the `EventFeed` interface, backed by
  the relay's `{lineups, statistics, fixture}` snapshot.
- A live-aware flow that sizes windows to the remaining half and waits on the real match
  clock between resolutions.
- A "waiting for live match" screen that ticks the live minute and polls the relay.
- Pre-match / no-lineup / half-already-over handling.
- Config: corrected relay path + a `live` block with the fixture id and poll cadence.
- Pure unit tests for the adapter and window-sizing against captured API JSON.

**Out (deferred to increment 2):**
- Two-player cooperative pick-sync via `soccer_api.php`. The live *data* is already shared
  (both clients reading the same match see the same numbers); exchanging picks for joint
  scoring is a separable follow-on.
- Live goal-by-goal events beyond what `fixtures` score + `fixtures/statistics` provide.

## Architecture

Reuses the established split: pure logic in `src/game/`, pygame only in `src/ui/`,
all constants in config. Three new/changed units:

### 1. `src/game/live_feed.py` -- `LiveFeed(EventFeed)`
The live sibling of `ReplayFeed`. Pure (no pygame, no direct network: it is *given*
snapshot dicts; fetching stays in `FeedClient`).
- `lineups()` -> engine athlete rows via the existing `normalize_soccer.parse_lineups`,
  **startXI only** (the 22-player draft pool; substitutes excluded so the pool matches the
  canned-sim shape).
- `record(snapshot_dict, elapsed_minute)` -- ingest one relay snapshot, building a
  cumulative `WindowSnapshot` keyed by the API-reported elapsed minute. Stats come from
  `normalize_soccer.parse_statistics` (corner_kicks, shots_on_goal, goalkeeper_saves,
  cards) **plus goals read from the `fixture` score** (home+away), so the `goal` stat is
  live rather than always 0.
- `snapshot_at(minute)` -- nearest recorded snapshot <= minute (same contract as
  `MockFeed`), so a window's actuals = end-snapshot - start-snapshot.
- `match_status_at(minute)` / `match_status()` -- maps the API status short code
  (`NS`, `1H`, `HT`, `2H`, `FT`, ...) to the engine's vocabulary; `HT` -> the configured
  `halftime_status` ("halftime"), so the existing `HalfClock.is_half_over` test works
  unchanged.
- `last_known_minute()` -- the latest elapsed minute recorded.

### 2. API status mapping (in `normalize_soccer` or `live_feed`)
A small pure map: `{"NS": "scheduled", "1H": "live", "HT": "halftime", "2H": "live",
"FT": "finished", ...}`. Unknown codes default to "live". This is the single place the
API's status vocabulary meets the engine's.

### 3. `src/ui/flow.py` -- `start_live(app, fixture_id)`
A live variant alongside `start()` and `start_simulation()`. The shared `Flow` is extended
(or subclassed) to:
- On start, fetch one snapshot, read the live elapsed minute + status, and compute the
  **lobby window** and the list of **remaining scored windows** (see model below).
- Run Splash -> Room -> Pre-game -> Draft during the lobby window (no wait, no score).
- For each remaining scored window: lock predictions, then show the **LiveWaitScreen**
  until the live match clock reaches the window's end (or `halftime` for ET), then snapshot,
  resolve (unchanged engine call), cinematic, next.
- End at the Half-Time summary, exactly as the current half-game does.

### 4. `src/ui/screens/live_wait_screen.py` -- `LiveWaitScreen`
Shown between locking predictions and resolving. Displays the live match clock and "waiting
for minute N". Drives polling: on `update(dt)` it accumulates time and, every
`feed.poll_seconds`, kicks a non-blocking relay fetch (integrated with the pygbag async
loop); when the recorded elapsed minute reaches the target (or status is `halftime`), it
fires its `on_ready` callback to resolve. Fetch failures keep the last good snapshot and
retry on the next tick.

## The remaining-half window model

`HalfClock(half_minutes=45, window_minutes=5)`: regular windows 1..9 cover minutes 0..45;
window 10 is Extra-Time (first-half stoppage), resolved by polling for `halftime`.

On start, read live elapsed minute `m` and status:

- **Pre-match** (`NS`, or `m == 0`): lobby is pre-kickoff; **all** windows 1..9 + ET are
  scored. Draft happens while the match is not yet live; predictions for window 1 lock at
  kickoff.
- **Live in first half** (`1H`, `0 < m < 45`): lobby window `w_cur = floor(m / 5) + 1`
  (e.g. m=23 -> window 5, minutes 20-25). The lobby is **not scored** -- it is draft +
  first-prediction time. Scored windows = `w_cur + 1 .. 9`, then ET.
  - m=23 -> lobby win 5; scored 6,7,8,9 + ET (5 scored windows).
  - m=43 -> lobby win 9; scored: ET only.
- **Half already over** (`HT`, `2H`, `FT`, or `m >= 45`): no scored windows remain; show a
  clean "first half is over" message and exit to a summary/Room.

Prediction cadence: predictions for the first scored window are made during the lobby; for
each later window they are made instantly at its start boundary, then the game waits ~5
real minutes for the match to play it out before resolving. Window actuals are the delta of
cumulative snapshots captured at the window's start and end boundaries.

## Wall-clock polling

- Poll cadence = `feed.poll_seconds` (120s), just over the relay's 110s cache TTL, so the
  shared free-tier quota is drawn once per cadence across both clients.
- The minute and status are **read from the API** each poll (never computed by local clock
  arithmetic), so stoppage/added time is handled by the feed.
- A window resolves on the first poll where reported elapsed >= window end (or status ==
  halftime for ET). Snapshots are recorded on every poll, and explicitly at lock time
  (window-start baseline) and at resolve time (window-end), so deltas are accurate.

## Goals handling

`fixtures/statistics` has no goals field; the `fixture` block carries the live score.
`LiveFeed.record` reads `goals = fixture.goals.home + fixture.goals.away` into each
cumulative snapshot, so `goal` predictions resolve live. (This closes the "goals resolve to
0" gap noted in `normalize_soccer.actuals_from_raw`.)

## Edge cases

- **No XI posted yet** (API publishes ~40 min before kickoff): the lineups array is empty;
  the live flow parks on a "lineups not released -- waiting" state and polls until startXI
  appears, then proceeds to the draft. Launching before kickoff therefore parks correctly.
- **Relay 503 / API error / empty response**: keep the last good snapshot; retry next tick.
  If no snapshot has ever arrived, stay on the waiting screen.
- **Match finished or at HT on start**: handled by the "half already over" branch above.

## Config changes (`config/game_config.json`)

- `relay.base_url`: `https://drpeterjamieson.com/game` ->
  `https://drpeterjamieson.com/PROJECTS/PREDICTOR/PHP_SCRIPTS`.
- New `live` block: `{ "fixture_id": <Scotland-Morocco id>, "competition_label":
  "FIFA World Cup 2026" }`. (`feed.poll_seconds` already exists.)
- The fixture id is resolved by a one-shot discovery query against API-Football (today's
  fixtures, filtered to Scotland vs Morocco) during implementation, and captured JSON is
  saved to `tests/fixtures/` for deterministic tests.

## Testing

- **Adapter (pure):** `LiveFeed.lineups()`, `record()`/`snapshot_at()` deltas, goals from
  score, and status mapping, all against captured `tests/fixtures/apifootball_*.json`
  (real shape, no network). Golden rule preserved -- no pygame in these tests.
- **Window sizing (pure):** lobby/scored-window computation for representative minutes
  (pre-match, 23', 43', HT) -- table-driven.
- **Wait loop:** driven by a fake transport returning a scripted minute sequence; assert the
  window resolves on the correct poll and survives an intermittent error.
- **End-to-end live:** run during the actual match (18:00 ET). Before kickoff the API
  returns `NS`/empty lineups and the build correctly parks on the waiting screen -- itself a
  valid check of the pre-match path.

## Follow-ons (not this increment)

1. Two-player cooperative pick-sync through `soccer_api.php`.
2. pygbag rebuild against the corrected relay path + redeploy of the PREDICTOR twin.
3. Optionally, second-half play.
