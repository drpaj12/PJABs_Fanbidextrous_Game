# Live Game Viewer -- Design Spec

**Date:** 2026-06-20
**Status:** Approved (brainstorming -> implementation)

## Goal

Replace the static, config-driven live-match picker with a dynamic viewer that reads a
hand-curated local schedule of World Cup + MLS games, orders upcoming games soonest-first,
shows each game's US Eastern kickoff time and a live "how soon" status, and lets the player
tap any not-yet-finished game to play it. The list scrolls (phone-first) and refreshes its
relative labels as time passes.

## Why a local JSON schedule (not an API / scrape)

The schedule is known ahead of time and changes rarely, so a curated JSON file is the
simplest robust source: zero API quota, no scrape fragility, works offline and in the WASM
build. Live match *data* (stats/score) still comes from API-Football once a game is tapped;
only the *schedule* (which games exist, when they start) is local.

## A. Data model -- `assets/data/schedule.json`

Loaded via the existing `load_data` helper (same path resolution as other `assets/data`
files, so it works under pygbag). One top-level `games` array. Each record:

```json
{
  "games": [
    { "id": 1539007, "competition": "FIFA World Cup 2026",
      "home": "Netherlands", "away": "Sweden", "round": "Group F",
      "kickoff_utc": "2026-06-20T21:00:00Z", "kickoff_local": "5:00 PM EDT" },
    { "id": 1539050, "competition": "FIFA World Cup 2026",
      "home": "", "away": "", "round": "Round of 16 - Match 50",
      "kickoff_utc": "2026-06-29T20:00:00Z", "kickoff_local": "4:00 PM EDT" }
  ]
}
```

Field rules:
- `id` (int): API-Football fixture id -- what the live play path already keys on.
- `competition` (str): label, e.g. "FIFA World Cup 2026" / "MLS".
- `home`, `away` (str): team names; may be `""` when the matchup is not yet known.
- `round` (str, required): a human descriptor ("Group F", "Round of 16 - Match 50").
  Used as the row title when `home`/`away` are blank, so every row always has a title.
- `kickoff_utc` (str, ISO 8601): drives ALL time math. UTC; "Z" or "+00:00" both accepted.
- `kickoff_local` (str): pre-baked US Eastern display string ("5:00 PM EDT"). No timezone
  logic in code -- the curator bakes EST/EDT correctness into this string. Math never uses it.

The curated file MAY hold a whole season; the rolling-window filter (Section B) keeps the
on-screen list short. This file REPLACES `config.live.fixtures` as the picker source. The
single-game `config.live.fixture_id` default (used by the `--live` desktop CLI flag) stays.

## B. Pure logic -- `src/game/schedule.py` (zero pygame)

A frozen dataclass plus pure functions. Every function that depends on the current time
takes `now` (epoch seconds) as a parameter, so behavior is deterministic and unit-testable.

```python
@dataclass(frozen=True)
class ScheduledGame:
    id: int
    competition: str
    home: str
    away: str
    round: str
    kickoff_utc: str
    kickoff_local: str

    def title(self) -> str:
        """'Home v Away' when both teams are known, else the round descriptor."""
        return f"{self.home} v {self.away}" if self.home and self.away else self.round

    def kickoff_epoch(self) -> Optional[float]:
        """kickoff_utc parsed to epoch seconds, or None if unparseable."""
```

Module functions (all take a `ScheduleConfig` of the four window numbers, or read them from
the passed config dict -- see Section D):

- `load_schedule(raw: dict) -> list[ScheduledGame]`
  Parse `raw["games"]`. Skip any record missing required keys or with an unparseable
  `kickoff_utc` (defensive: a bad row never crashes the picker).

- `game_status(game, now, live_window_minutes) -> str`
  `"upcoming"` if `now < kickoff`; `"live"` if `kickoff <= now < kickoff + live_window`;
  `"final"` if `now >= kickoff + live_window`. (`live_window_minutes` is generous --
  covers two halves + stoppage + halftime, default 150 -- since the viewer does not poll
  the API to learn real full-time.)

- `status_label(game, now, soon_minutes, live_window_minutes) -> str`
  - upcoming, > soon_minutes away: `"in 2h"`, `"in 1d"`, `"in 15m"` (largest whole unit:
    days if >= 24h, else hours if >= 60m, else minutes).
  - upcoming, <= soon_minutes away: `"soon"`.
  - live: `"LIVE NOW"`.
  - final: `"Final"`.

- `is_playable(game, now, live_window_minutes) -> bool`
  `game_status(...) != "final"`. (Upcoming AND live games are tappable, per design.)

- `visible_games(games, now, cfg) -> list[ScheduledGame]`
  Keep games where `-drop_after_hours*3600 <= (kickoff - now) <= lookahead_hours*3600`
  (i.e. from `drop_after_hours` after kickoff, back through `lookahead_hours` before it),
  sorted by `kickoff_epoch` ascending. Games with no parseable kickoff are dropped.

## C. UI -- dynamic `FixtureSelectScreen`

Rebuild the picker (`src/ui/screens/fixture_select_screen.py`) as a scrollable list,
reusing the existing `ScrollButtons` widget + clipped-viewport + integer `scroll` offset
pattern already used in `src/ui/screens/draft_screen.py`.

Constructor gains the parsed games and a `now_fn` (injected clock, defaulting to
`time.time`, mirroring the live screens) so relative labels update over time:

```python
def __init__(self, app, games: list[ScheduledGame], on_pick: Callable[[int], None],
             cfg: dict, sim=None, now_fn: Callable[[], float] = time.time) -> None
```

Each frame:
- Compute `visible = visible_games(self.games, now_fn(), cfg)`. (Cheap; small list.)
- Render one card per visible game inside the scroll viewport:
  - Line 1: `game.title()`.
  - Line 2: `game.kickoff_local` (dim).
  - Right side: status chip from `status_label(...)`, colored -- `live` accent, `upcoming`
    white/dim, `final` greyed.
- Playable cards (`is_playable`) are tappable -> `on_pick(game.id)`. `final` cards draw
  greyed and ignore taps.
- Empty state: if `visible` is empty, draw a centered "No games scheduled right now --
  check back later" message; no cards, no scroll buttons.
- Scroll: `ScrollButtons` in the right gutter + wheel support (as draft screen). Buttons
  draw only when content exceeds the viewport.
- SIM: auto-pick the first PLAYABLE visible game (so the headless/demo path keeps moving);
  if none playable, do nothing (let the smoke detect the empty/non-playable case).

Tapping calls the existing `on_pick`, which enters the existing `start_live` flow unchanged
-- the pre-game lobby (`LiveWaitScreen` + `kickoff_phase`) already handles
too-early/countdown/live, so the viewer adds no new waiting logic.

## D. Wiring, config, errors, testing

**Wiring (`src/ui/flow.py`):** `start_live_select` loads `schedule.json` via `load_data`,
parses with `load_schedule`, and constructs `FixtureSelectScreen(app, games, picked, cfg,
sim)` (passing `CONFIG["live"]["schedule"]` as `cfg`). `picked(id)` calls `start_live(...)`
exactly as today. `config.live.fixtures` is no longer read by the picker (left in config or
removed -- see plan).

**Config -- new `live.schedule` block (`config/game_config.json`):**
```json
"schedule": {
  "file": "schedule.json",
  "lookahead_hours": 48,
  "drop_after_hours": 4,
  "live_window_minutes": 150,
  "soon_minutes": 15
}
```
(`file` is the `assets/data` basename; the four numbers are the only tunables. No magic
numbers in code -- all read from config.)

**Errors / robustness:**
- Missing or unreadable schedule file, empty `games`, or zero visible games -> the screen's
  empty-state message (never a blank or crashing screen).
- Malformed individual records (missing key, bad timestamp) are skipped in `load_schedule`
  / `visible_games`, not fatal.
- All status math is wall-clock vs `kickoff_utc`; `"Final"` is a time heuristic (game is
  past its live window). Real full-time is still determined by the live feed after tap, so a
  game in long stoppage is never prematurely un-playable beyond the generous `live_window`.

**Testing -- `tests/test_schedule.py` (no pygame):**
- `title()`: known teams -> "A v B"; blank teams -> round descriptor.
- `kickoff_epoch`: valid ISO ("Z" and "+00:00") parse equal; bad string -> None.
- `game_status`: just-before kickoff -> upcoming; at kickoff -> live; last second of live
  window -> live; one second past -> final.
- `status_label`: minutes (`"in 15m"`), hours (`"in 2h"`), days (`"in 1d"`), `soon`
  threshold boundary, `LIVE NOW`, `Final`.
- `is_playable`: true for upcoming + live, false for final.
- `visible_games`: includes a game `lookahead_hours` ahead and one `drop_after_hours` after
  kickoff; excludes one beyond each edge; result sorted soonest-first; drops a bad-kickoff
  record.
- `load_schedule`: parses a good file; skips a record missing `round` / with bad timestamp.

**Headless smoke (`TOOLS/smoke_flow.py`):** extend the offline/live smokes with a tiny
schedule-screen check -- build a `FixtureSelectScreen` from a synthetic games list + a fixed
`now_fn`, assert the visible/sorted/playable set matches expectation and that SIM auto-picks
the first playable game's id.

## Out of scope (YAGNI)

- No live polling in the viewer (status is time-based until a game is tapped).
- No auto-refresh of the schedule file from any network source (it is hand-curated).
- No persistence of "last viewed" or favorites.
- No timezone library / DST computation in code (curator bakes `kickoff_local`).

## File summary

- Create: `assets/data/schedule.json`, `src/game/schedule.py`, `tests/test_schedule.py`
- Modify: `src/ui/screens/fixture_select_screen.py`, `src/ui/flow.py`,
  `config/game_config.json`, `TOOLS/smoke_flow.py`
