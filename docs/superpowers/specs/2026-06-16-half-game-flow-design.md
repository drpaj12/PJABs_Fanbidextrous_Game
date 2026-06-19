# Half-Game Flow Design

**Status:** approved (design), pending spec review
**Date:** 2026-06-16
**Author:** PJAB + Claude

## Goal

Turn the local single-device game from a 3-window demo into a faithful **first
half**: a pre-game lobby, the draft, **9 five-minute prediction windows**
(minutes 0-45), then **one Extra-Time window** settled over all first-half
stoppage, then a **Half-Time summary**. Built so the same flow runs off recorded
simulation data today and an unmodified live feed at deployment.

## Motivation

The `--simdemo` MockFeed script ends at minute 15 = only 3 windows. Replay sims
carry a full 96-minute match but nothing models a half whose stoppage length is
unknown until the whistle. The half is the unit we will deploy, so the local
flow must already behave the way the live game will: it discovers half-time by
polling, never by reading a pre-known stoppage length.

## Match structure

- `window_seconds` = 300 (5 min). `half_minutes` = 45. Regular windows =
  `half_minutes // window_min` = **9** (numbered 1-9, covering minutes 0-45).
- Each window: one feed query at its boundary; predict all 5 stats; resolve
  against the stat delta across the window. (Unchanged from today, just looped 9x.)
- After window 9 (minute 45): **one Extra-Time window**. Normal all-5-stat
  PlayScreen, header labelled "Extra Time". Stoppage length is NOT known when the
  player locks in.
- The flow then advances the feed forward from minute 45, polling match status,
  until the feed reports the first half has ended (**half-time**). Stoppage may
  extend ("extra extra time"); polling simply continues. The ET window resolves
  **once**, against the stat delta from minute 45 to the half-time snapshot
  (all stoppage, however long).
- Then a **Half-Time summary** screen (the existing FinalScreen, worded "Half
  Time" instead of "Full Time").

## Live / simulation parity

The flow treats the feed as a live oracle that reveals data progressively. It
must NOT read the stoppage length ahead of time; it discovers half-time by
polling `match_status`. Recorded sim files carry a half-time status entry, so the
sim discovers stoppage by polling exactly as the live client will against the
API-Football status codes (`1H` in progress / `HT` half ended). The only thing
that changes at deployment is the feed implementation; the flow code is identical.

## Pre-game placement

**Lobby after the menu:** Room -> Pre-game -> Draft. The pre-game screen shows
the fixture (teams / competition / "First Half") and a Start button. Replay sims
read titles from `ReplayFeed.meta`; the demo MockFeed uses a default fixture.

## Components / files

- `config/game_config.json`: add `game.half_minutes` (45), `game.half_label`
  ("First Half"), `game.extra_time_label` ("Extra Time"),
  `feed.halftime_status` ("halftime"). No stoppage-length constant -- its absence
  is intentional.
- `config/layout_config.json`: pre-game screen layout keys (fixture title, lines,
  start button) and an optional play-screen phase-label position.
- `src/game/half_clock.py` (new, pure Python): given a window index returns its
  `[start_min, end_min]`; reports whether a window is the extra-time phase;
  decides "is the half over?" from a feed status string. Fully unit-tested.
- `src/game/mock_feed.py` / `replay_feed.py`: a half-time status concept --
  `match_status_at(minute)` can return `halftime`; a `first_half_end_minute()`
  helper (sim convenience; the flow still discovers it by polling, not by reading
  it ahead). ReplayFeed exposes its first-half-end marker.
- `src/ui/screens/pregame_screen.py` (new): fixture lobby; SIM auto-advances.
- `src/ui/screens/play_screen.py`: accept an optional `phase_label` shown in the
  header (e.g. "Extra Time"); otherwise unchanged (still all-5 predictions).
- `src/ui/screens/status_screens.py`: FinalScreen gains a `title` param so the
  half-game can show "Half Time".
- `src/ui/flow.py`: insert pre-game after Room; loop 9 windows; run the ET window;
  poll the feed to half-time to resolve ET; go to Half-Time summary.
- Demo MockFeed script (`_demo_script`): extend to a full first half (minutes
  0-45 + a few stoppage minutes) with a `halftime` status entry.

## Extra-time resolution (data flow)

1. Player locks ET predictions at minute 45.
2. Flow enters a "watching stoppage" state: repeatedly advance the feed clock and
   check `match_status` (sim: minute-by-minute / per poll; live: real polls on the
   existing cadence).
3. When status is half-time at minute H: actuals = feed delta (45 -> H). Resolve
   the ET window once; build the WindowReport (labelled Extra Time).
4. Show the Half-Time summary.

## Edge cases

- **Stoppage = 0** (half ends exactly at 45): ET resolves over a zero-length
  delta (all actuals 0) -- still a real window, just an empty one.
- **Extended stoppage:** polling continues; one resolution covers all of it.
- **Live feed has not reported half-time yet:** keep polling on cadence; the ET
  window stays open until half-time. The sim data guarantees a half-time marker.

## Testing

- `half_clock` unit tests: window ranges (1 -> [0,5], 9 -> [40,45]); ET phase
  detection; half-over decision from a status string.
- Feed tests: `halftime` status read from a script; delta across stoppage.
- `TOOLS/smoke_flow.py`: both paths (demo + replay) reach Half-Time after 9 + ET
  windows.

## Out of scope (next milestone)

The live web deployment itself -- API-Football key placement, PHP relay/proxy
deploy, two-client sync, pygbag HTML clients. Tracked as the follow-on task; the
LiveFeed adapter slots into the same EventFeed interface this design preserves.

### Deployment layout (recorded for the follow-on task)

Everything lives under **`drpeterjamieson.com/PROJECTS/PREDICTOR/`** -- keys,
scripts, pygbag build, all of it. Layout:

```
PROJECTS/PREDICTOR/
  index.html              <- 404-style page (deters directory browsing)
  <pygbag build files>    <- the web clients
  PHP_SCRIPTS/
    index.html            <- 404-style page
    apifootball_key.txt   <- server-side only, never web-served
    soccer_api.php
    feed_cache.php
    sync.php
```

- Every directory gets an `index.html` that renders a 404-style "Not Found" page
  so the directory contents are not browsable. (A true HTTP 404 status would need
  an `.htaccess` rule; the index page is the baseline obscurity measure.)
- Relay endpoints therefore become
  `https://drpeterjamieson.com/PROJECTS/PREDICTOR/PHP_SCRIPTS/sync.php` (and
  `soccer_api.php`, `feed_cache.php`). The client `relay.base_url` config points
  here. (Supersedes the older `/game/` path noted in CLAUDE.md.)
