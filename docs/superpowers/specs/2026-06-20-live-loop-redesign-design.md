# Live Loop Redesign -- Design Spec

Date: 2026-06-20
Status: Approved (brainstorm complete, ready for plan)
Supersedes the live-play portions of: 2026-06-19-live-single-player-design.md

## Goal

Replace the turn-based live half (predict screen -> blocking wait screen -> full-screen
cinematic, repeated per window) with a single always-running live screen driven by a
wall-clock match clock. The player always edits the NEXT window's prediction while the
current window plays out; windows auto-lock and resolve inline as the clock crosses each
boundary. Cut API usage to the minimum and survive losing browser focus and app restarts.

This came out of the first live playtest. It covers the core live loop (A) and the
stat-menu cleanup (B). The dynamic upcoming-match picker (C) is a separate spec.

## Decisions locked during brainstorming

1. Scope: full redesign, quality over hitting today's kickoff.
2. Deadline rule: at each window boundary, whatever sits on the dials AUTO-LOCKS. There is
   no manual "lock to advance" step; the clock advances on its own.
3. Stat set: drop Saves (it is "shots on target minus goals" -- redundant), add Fouls.
   Final five: Goals, Shots on target, Corners, Cards, Fouls.
4. Result reveal: inline on the live screen (meters tick, banner flash, panel flips the
   resolved window to its scored line). No full-screen takeover. 5 minutes per window is
   long enough that the last window's animation can play out before the next boundary.
5. Warm cache keyed by username + fixture id.
6. Kickoff times come from config (stopgap until the match-picker lands).

---

## 1. The timing model

### 1.1 Windows and boundaries

Windows are the existing 5-minute tiles from HalfClock: W1 = 0-5', W2 = 5-10', ...,
W9 = 40-45', plus one Extra-Time window for first-half stoppage. The locking moments are
the boundaries at minutes 0, 5, 10, ... .

The player is ALWAYS editing one window ahead of the window that is playing:

| Clock reaches      | Auto-locks | Resolves (inline) | Now editing |
|--------------------|------------|-------------------|-------------|
| before 0' (lobby)  | --         | --                | W1 (0-5')   |
| 0' (kickoff)       | W1         | --                | W2 (5-10')  |
| 5'                 | W2         | W1                | W3 (10-15') |
| 10'                | W3         | W2                | W4          |
| ...                | ...        | ...               | ...         |
| half over (API HT) | (last ET)  | ET window         | -- (final)  |

At boundary minute 5K (K >= 1): window K resolves, window K+1 auto-locks, editing moves to
window K+2. At minute 0: window W1 auto-locks (nothing to resolve yet), editing moves to W2.

### 1.2 Joining mid-half

The first editable window is the first window whose start minute is still in the future at
join time (reuses live_schedule.live_plan to know which windows remain scored). Windows that
already started before the player joined are skipped -- the player cannot affect them.

### 1.3 Wall clock decides timing; the API decides the numbers

- Match minute = floor((now - kickoff_epoch) / 60), clamped at 0, ticked locally every frame.
  Needs nothing from the API. This is the "clock running with the score without hammering the
  API."
- Window results use the API stat deltas between the snapshots nearest the window's start and
  end minutes (existing LiveFeed.snapshot_at + actuals_from_raw machinery, unchanged).
  Between polls the clock keeps moving and the score shows the last polled value.
- Halftime / end of the Extra-Time window still comes from the API status (stoppage length
  is unknowable locally). The ET window resolves when status == halftime, same as now.

---

## 2. Wall-clock engine (focus-proof)

### 2.1 New pure module: src/game/match_clock.py

A pure dataclass (no pygame, no I/O, fully unit-tested) that, given kickoff epoch seconds
and "now" epoch seconds, answers:

- current_minute(now) -> int
- playing_window(now) -> int            (the window currently in progress; 0 before kickoff)
- editing_window(now) -> int            (playing_window + 1, the one the player edits)
- boundaries_crossed(prev_now, now) -> list[int]
      window indices whose END boundary fell in (prev_now, now]; the screen uses this each
      frame to know which windows to lock+resolve. Usually empty; one entry at a boundary.

It composes with the existing HalfClock for window_start / window_end / extra_time math.
The Extra-Time boundary is not time-based (discovered via API halftime status), so
boundaries_crossed only covers regular windows; the ET resolve is triggered by status.

### 2.2 Wall-clock anchored polling

Replace the dt-accumulator (which freezes when the tab is backgrounded) with a wall-clock
timestamp of the last poll. Poll fires when now - last_poll_epoch >= poll_seconds. On focus
regain, now has jumped, the condition is true, and it polls immediately -- losing focus can
never strand the feed. The lead-client quota gate is unchanged.

---

## 3. The unified live screen

### 3.1 New screen: src/ui/screens/live_play_screen.py

One screen up for the whole half. It absorbs the live roles of PlayScreen (predict) and
LiveWaitScreen (wait/poll). The pre-kickoff countdown becomes its lobby phase (reusing the
existing kickoff.py countdown/too-early/soon logic).

Regions, top to bottom:
- Header: running match clock (wall-clock) + current score + match status.
- Active editor: the window the player is filling in, with the five stat dials (-/+ steppers)
  and the active-player picker. This is the only editable region.
- Predictions panel: locked windows, newest first, each showing the line number above each
  stat code. A just-resolved window shows its scored line briefly, then collapses to a
  one-line result.
- Force-update button ("Update now").

Pre-kickoff lobby phase: shows the kickoff countdown (from config kickoff time, zero API
calls) and lets the player set W1's dials. At kickoff, W1 auto-locks.

### 3.2 Predictions panel content

For each locked window: window label (e.g. "W2 5-10'"), the per-stat line numbers with the
stat code beneath, and a status (LOCKED while in flight; the scored summary once resolved).
The actively edited window sits in the editor region above, not in the panel.

### 3.3 Force-update button

Calls the same poll path immediately and resets the wall-clock poll timer. Subject to the
lead gate: a follower's force-update reads the relay cache; only the lead triggers an
upstream fetch. Cannot exceed quota.

### 3.4 Inline result reveal

When boundaries_crossed reports a finished window: resolve it (session.resolve_window, pure,
unchanged), build the WindowReport and the cinematic SCRIPT (build_cinematic_script reused),
and render the reveal inline -- meters tick, a banner flashes (GOAL! / result), the panel
flips that window to its scored line -- while the clock keeps running. No screen change.

---

## 4. Stat-menu cleanup

assets/data/stats_menu.json becomes:

| code   | label            | kind     | api_field      | default_line |
|--------|------------------|----------|----------------|--------------|
| goal   | Goals            | incident | goals          | 1            |
| shot   | Shots on target  | delta    | shots_on_goal  | 2            |
| corner | Corners          | delta    | corner_kicks   | 3            |
| card   | Cards            | incident | cards          | 1            |
| foul   | Fouls            | delta    | fouls          | 4            |

Save (goalkeeper_saves) is removed; Fouls (api_field "Fouls" in API-Football statistics) is
added. normalize_soccer must map the API "Fouls" statistic into the "fouls" key. The scoring
engine iterates whatever stats are in the menu, so resolve_window, WindowReport, and the
meters need no logic change -- only the data and the normalize mapping change.

default_line 4 for fouls is a first guess (fouls are frequent); tune after a live half.

---

## 5. Quota and persistence

Three layers, each cutting calls:

### 5.1 Kickoff time from config (no API call to learn it)

Each entry in config.live.fixtures gains a "kickoff" ISO-8601 timestamp. The pre-game
countdown reads it directly -- zero API calls before the 15-minute gate. Today's first
kickoff is 2026-06-20T17:00:00+00:00 (Netherlands v Sweden, 1539007); the other two are
filled at implementation time from a single fixtures lookup (or supplied by the user). The
match-picker (sub-project C) will supply these automatically later.

### 5.2 Lineups gated to start_minutes_before (15 min)

The first API call of the day happens ~15 min before kickoff, to fetch the starting XI.
Nothing is fetched earlier. This is already the rule (live.start_minutes_before); the change
is removing the one "initial poll to learn kickoff time" that used to sneak in ahead of it
(now unnecessary because kickoff time is in config).

### 5.3 Client-side warm cache keyed by username + fixture id

Every successful poll is written to persistent storage (browser localStorage in WASM; a
small JSON file on desktop) under a key derived from username + fixture id. The stored blob
holds the last fixture/lineups/stats snapshot and the last poll epoch.

On app start, the cache is loaded BEFORE any network call:
- last-known lineups, score, and clock render instantly;
- no API call is made to re-learn anything already cached;
- live polling resumes only for genuinely new data (the next 5-min window), still gated and
  still behind the relay cache.

A restart with the same username + fixture therefore costs zero extra API calls.

### 5.4 Architecture of the cache

- Pure policy (src/game/feed_cache_policy.py, tested): serialization of the cache blob and
  the staleness/merge rules (what to keep, when a cached snapshot is too old to trust for
  live scoring vs. fine for warm display).
- Platform I/O (src/sync/local_store.py): key/value persistence. WASM -> localStorage via
  the pygbag platform bridge; desktop -> JSON file under a known dir. Import-safe (the WASM
  bits imported lazily), mirroring the wasm_transport pattern.

### 5.5 Relay cache unchanged

The server relay cache (feed_cache.php, per-fixture TTL) stays as the cross-client guard:
followers free-ride; the lead's repeat polls within TTL do not hit upstream.

Net effect for the lead: one lineup fetch + roughly one fetch per 5-min window; a restart
costs zero extra calls.

---

## 6. File and test plan

New (pure logic, no pygame, tested):
- src/game/match_clock.py -- the wall-clock window engine (section 2.1).
- src/game/feed_cache_policy.py -- cache blob serialization + staleness rules (section 5.4).

New (platform I/O):
- src/sync/local_store.py -- localStorage (WASM) / JSON file (desktop), import-safe.

New (UI):
- src/ui/screens/live_play_screen.py -- the unified always-running screen (section 3).

Rewritten:
- LiveFlow in src/ui/flow.py -- drives the single screen across the whole half instead of
  predict -> wait -> resolve per window. start_live keeps the lobby -> (lineups) -> play
  shape but the play phase is now one screen.

Data / config:
- assets/data/stats_menu.json -- the new five stats (section 4).
- config/game_config.json -- kickoff timestamps in live.fixtures; any new persistence keys.
- src/game/normalize_soccer.py -- map API "Fouls" into the "fouls" key.

Retired / reduced:
- LiveWaitScreen's live wait/poll role moves into live_play_screen. Its pre-game countdown
  logic is reused (either kept as a lobby helper or folded into the new screen). PlayScreen
  stays for the offline/sim and mock single-device Flow (non-live) paths.

Tests:
- test_match_clock.py -- minute, playing/editing window, boundaries_crossed across kickoff,
  mid-half join, and the ET edge.
- cache-policy tests -- round-trip serialization, staleness rules.
- normalize/report tests updated for fouls (and saves removed).
- Existing 125 tests stay green.

Golden-rule compliance: all new game logic is pygame-free and tested; all I/O and pygame
live in src/sync and src/ui; no magic numbers (window length, poll cadence, stat lines,
gates all stay in config).

---

## 7. Out of scope (separate specs)

- C: dynamic upcoming-match picker (MLS / EPL / World Cup, scrollable, EST kick times) --
  its own spec; it will later feed the kickoff times that section 5.1 now hardcodes.
- The desktop/mobile aspect-ratio web-layout fix (414x896) -- a small independent task,
  tracked separately.
- Two-player relay sync of picks (still deferred).
