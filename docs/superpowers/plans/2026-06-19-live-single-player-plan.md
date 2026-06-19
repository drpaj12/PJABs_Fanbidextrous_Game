# Live Single-Player Build Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Pure-logic
> tasks (1-5) are TDD with `tests/`. UI/flow tasks (6-8) follow CLAUDE.md's increment loop
> (write -> `pytest` -> launch -> log). All output ASCII-only. Use `.venv/Scripts/python`.

**Goal:** One player plays the half-game against the live Scotland vs Morocco match, with
lineups + stats from API-Football via the PHP relay, windows sized to what's left in the
half, advancing in real wall-clock time.

**Architecture:** New pure `LiveFeed` (sibling of `ReplayFeed`) fed by the existing
`FeedClient`; pure window-sizing helper; a `LiveWaitScreen` that polls the relay across
frames via `asyncio.ensure_future`; a `start_live` flow variant. Engine + scoring untouched.

**Tech Stack:** Python 3.11, pygame-ce, pygbag async loop, API-Football v3 via `feed_cache.php`.

---

### Task 1: Resolve fixture id + capture real API JSON + config

**Files:**
- Modify: `config/game_config.json` (relay.base_url, new `live` block)
- Create: `tests/fixtures/apifootball_lineups_real.json`, `apifootball_statistics_real.json`,
  `apifootball_fixture_real.json` (captured)
- Use: key at `WEB_BUILD/PREDICTOR/PHP_SCRIPTS/apifootball_key.txt`

- [ ] **Step 1:** Discovery query against `https://v3.football.api-sports.io/fixtures` for
  today's Scotland vs Morocco (search by team + date, league = World Cup 2026). Record the
  fixture id. If the free tier does not serve it, fall back to `/fixtures?live=all` during
  the match window and match by team names.
- [ ] **Step 2:** Capture `fixtures/lineups`, `fixtures/statistics`, and `fixtures?id=` JSON
  for that id into `tests/fixtures/` (extend `scripts/capture_fixtures.py` to also save the
  `fixtures?id=` payload as `apifootball_fixture_real.json`).
- [ ] **Step 3:** Set `relay.base_url` to
  `https://drpeterjamieson.com/PROJECTS/PREDICTOR/PHP_SCRIPTS`; add
  `"live": {"fixture_id": <id>, "competition_label": "FIFA World Cup 2026"}`.
- [ ] **Step 4:** Commit.

Note: if the match is pre-kickoff, lineups/statistics may be empty `response: []`. Capture
anyway (it exercises the empty path) and re-capture a live sample during the match if possible.

---

### Task 2: API status mapping (pure)

**Files:** Modify `src/game/normalize_soccer.py`; Test `tests/test_normalize_soccer.py`

- [x] **Step 1:** Test: `map_status("HT")` -> the configured `halftime_status`;
  `"1H"`/`"2H"` -> `"live"`; `"NS"` -> `"scheduled"`; `"FT"`/`"AET"`/`"PEN"` -> `"finished"`;
  unknown -> `"live"`.
- [x] **Step 2:** Implement `map_status(short: str) -> str` with a dict + default, reading the
  halftime token from `CONFIG["feed"]["halftime_status"]`.
- [x] **Step 3:** `pytest` that test. **Step 4:** Commit.

---

### Task 3: `LiveFeed` (pure)

**Files:** Create `src/game/live_feed.py`; Test `tests/test_live_feed.py`

Implements the `EventFeed` interface from one or more relay snapshots. A relay snapshot is
the `feed_cache.php` shape: `{"lineups": <api>, "statistics": <api>, "fixture": <api>,
"cached_at": ...}`.

- [x] **Step 1:** Test `lineups()` against captured JSON returns **startXI only** (22 rows),
  each with name / broad position / jersey, using `normalize_soccer.parse_lineups` filtered
  to the `startXI` group. (Add a `groups` arg to `parse_lineups`, default unchanged, so
  `LiveFeed` can request `("startXI",)` without breaking existing callers.)
- [x] **Step 2:** Test `record(snapshot, minute)` then `snapshot_at(minute)`: stats from
  `parse_statistics` plus `goals` = `fixture.response[0].goals.home + .goals.away`; a later
  minute's snapshot minus an earlier one yields correct deltas; `snapshot_at` returns nearest
  recorded <= minute.
- [x] **Step 3:** Test `match_status_at`/`match_status` use `map_status` on
  `fixture.response[0].fixture.status.short`; `last_known_minute()` returns the max recorded
  elapsed minute; `current_minute()` returns the live elapsed from the latest fixture payload.
- [x] **Step 4:** Implement `LiveFeed` (no pygame, no network). Constructor takes nothing or
  an optional first snapshot; `record(snapshot, minute=None)` derives minute from
  `status.elapsed` when not given.
- [x] **Step 5:** `pytest`. **Step 6:** Commit.

---

### Task 4: Live window-sizing (pure)

**Files:** Create `src/game/live_schedule.py`; Test `tests/test_live_schedule.py`

- [x] **Step 1:** Test `live_plan(elapsed, status, clock)` returns
  `{lobby_window, scored_windows}` for: pre-match (`NS`/elapsed 0) -> lobby 0 (pre-kickoff),
  scored `[1..9, ET]`; elapsed 23 `1H` -> lobby 5, scored `[6,7,8,9,ET]`; elapsed 43 -> lobby
  9, scored `[ET]`; `HT`/elapsed>=45 -> lobby None, scored `[]`.
- [x] **Step 2:** Implement using `HalfClock`: `w_cur = elapsed // window_minutes + 1` for
  live; pre-match lobby = 0; half-over -> empty. ET = `clock.extra_time_window`.
- [x] **Step 3:** `pytest`. **Step 4:** Commit.

---

### Task 5: `FeedClient` minute/status helpers (pure-ish)

**Files:** Modify `src/sync/feed_client.py`; Test `tests/test_feed_client.py` (fake transport)

- [x] **Step 1:** Test with a fake `Transport` returning captured snapshot JSON that
  `get_feed(id)` returns the dict unchanged (already true) and add a guard returning `{}` on
  malformed JSON. Keep it thin -- parsing lives in `LiveFeed`.
- [x] **Step 2:** `pytest`. **Step 3:** Commit (skip if no change needed beyond a test).

---

### Task 6: `LiveWaitScreen` (UI)

**Files:** Create `src/ui/screens/live_wait_screen.py`

- [x] **Step 1:** Implement a `Screen` showing the live match clock and "waiting for minute
  N". Constructor: `(app, feed: LiveFeed, feed_client: FeedClient, fixture_id, target_minute,
  on_ready, poll_seconds)`. `target_minute=None` means "wait for halftime" (ET) or "wait for
  lineups" (pre-draft).
- [x] **Step 2:** `update(dt)`: accumulate dt; if no fetch in flight and (never polled or
  accumulator >= poll_seconds), set in-flight and `asyncio.ensure_future(self._poll())`.
  After data arrives, if the ready condition holds (`feed.current_minute() >= target_minute`,
  or status == halftime, or lineups present) call `on_ready()` once.
- [x] **Step 3:** `_poll()` coroutine: `snap = await feed_client.get_feed(fixture_id)`;
  `feed.record(snap)`; clear in-flight; reset accumulator. Guard exceptions -> keep last good,
  clear in-flight.
- [x] **Step 4:** Launch desktop to confirm the screen renders (it will sit waiting against
  the real relay/pre-match). **Step 5:** Append to `log.md`. **Step 6:** Commit.

---

### Task 7: `start_live` flow + entry points

**Files:** Modify `src/ui/flow.py`, `src/main.py`; (web) note for `main.py`/`demo_flow`

- [x] **Step 1:** `flow.start_live(app, fixture_id, sim_mode=False)`: build a `LiveFeed` +
  `FeedClient(CONFIG["relay"]["base_url"], feed_path=CONFIG["relay"]["feed_path"])`; do an
  initial poll via a pre-draft `LiveWaitScreen` (wait for lineups), then compute `live_plan`
  from `feed.current_minute()/match_status()`.
- [x] **Step 2:** Extend `Flow` so the window sequence is driven by `scored_windows` from the
  plan instead of incrementing 1..10: pool from `feed.lineups()`; after draft, iterate the
  scored list; before each resolve, push a `LiveWaitScreen(target=clock.window_end(w))`
  (or halftime for ET) whose `on_ready` calls the existing `_after_predict` path with
  `_window_actuals()` reading `snapshot_at(start)`/`snapshot_at(end)`.
- [x] **Step 3:** Handle the half-over plan (empty scored list) -> `FinalScreen` titled
  "First Half Over" / Room.
- [x] **Step 4:** Add `--live` to `src/main.py` -> `flow.start_live(app, CONFIG["live"]["fixture_id"])`.
- [x] **Step 5:** `pytest` (engine untouched -> still green); launch `--live` to verify it
  reaches the waiting screen and, if lineups exist, the draft. **Step 6:** `log.md`. Commit.

---

### Task 8: Final review + verification

- [x] **Step 1:** Full `pytest` green; `src/main.py` (demo) still launches; `--sim` still works.
- [x] **Step 2:** Confirm golden rule: no pygame import in any `src/game/` file; tests touch
  only `src/game`/`src/sync`.
- [ ] **Step 3:** During the 18:00 ET match: run `--live`, draft real players, watch a window
  resolve in real time. Record result in `log.md`.
- [x] **Step 4:** Final commit.

---

## Follow-ons (separate plans)
1. Two-player pick-sync via `soccer_api.php`.
2. pygbag rebuild against corrected relay path + redeploy PREDICTOR twin (web `main.py`
   currently uses `demo_flow`; add a live launch path there too).
