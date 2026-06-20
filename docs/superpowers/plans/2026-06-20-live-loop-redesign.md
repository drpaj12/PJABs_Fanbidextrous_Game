# Live Loop Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the turn-based live half (predict -> blocking wait -> full-screen cinematic, per window) with one always-running live screen driven by a wall-clock match clock, with predict-ahead auto-lock, inline result reveal, a cleaned-up stat set, and minimal/persistent API usage.

**Architecture:** A new pure `MatchClock` (kickoff + now -> minute/window math) and a pure `feed_cache_policy` drive a new `LivePlayScreen` that stays up for the whole half. A platform `LocalStore` persists the last snapshot per username+fixture. `LiveFlow` is rewritten to host the single screen and poll on the wall clock. The pure scoring engine (`GameSession.resolve_window`), `WindowReport`, and the cinematic *script builder* are reused unchanged; only rendering moves inline.

**Tech Stack:** Python 3.11, pygame-ce, pygbag/WASM, pytest. All commands use `.venv/Scripts/python`. ASCII-only in all printed/logged/`.md` output.

**Source of truth:** `docs/superpowers/specs/2026-06-20-live-loop-redesign-design.md`.

---

## Pre-flight (read once before Task 1)

- This is NOT a git worktree task; work on `main` (solo dev, see project memory).
- Run tests with: `.venv/Scripts/python -m pytest tests/ -q`. Baseline is 125 passing.
- Launch check (after UI tasks): `.venv/Scripts/python src/main.py` must open the window.
- NEVER use bare `python`. NEVER import pygame under `src/game/`. No magic numbers -- new
  constants go in `config/game_config.json` and load via `src/utils/constants.py`.
- After each task: append one line to `log.md` as `YYYY-MM-DD | what | files`.

### File map (what each new/changed file owns)

| File | Responsibility | pygame? |
|------|----------------|---------|
| `src/game/match_clock.py` (new) | kickoff+now -> minute, playing/editing window, windows entered | no |
| `src/game/feed_cache_policy.py` (new) | warm-cache blob: key, (de)serialize, start-poll decision | no |
| `src/sync/local_store.py` (new) | persist key/value: localStorage (WASM) / JSON file (desktop) | no |
| `src/ui/screens/live_play_screen.py` (new) | the unified always-running live screen | yes |
| `assets/data/stats_menu.json` (edit) | the five predictable stats (drop save, add foul) | n/a |
| `config/game_config.json` (edit) | fixture kickoff times; cache config keys | n/a |
| `src/ui/flow.py` (edit) | rewrite `LiveFlow` + `start_live` to host the one screen | yes |

---

## Task 1: Stat-menu cleanup (drop Saves, add Fouls)

**Files:**
- Modify: `assets/data/stats_menu.json`
- Test: `tests/test_stats_menu.py` (new)

Fouls is already plumbed: `normalize_soccer._STAT_FIELD` maps `"Fouls" -> "fouls"`, and
`actuals_from_raw` maps each menu stat's `api_field` to its `code`. So this is a data change
plus a guard test that the menu is well-formed and the engine bridge resolves fouls.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stats_menu.py`:

```python
import json
from pathlib import Path
from src.game.normalize_soccer import actuals_from_raw

_MENU = json.loads(
    (Path(__file__).resolve().parents[1] / "assets/data/stats_menu.json").read_text())


def test_menu_is_the_five_agreed_stats():
    codes = [s["code"] for s in _MENU["stats"]]
    assert codes == ["goal", "shot", "corner", "card", "foul"]
    assert "save" not in codes


def test_every_stat_has_required_keys():
    for s in _MENU["stats"]:
        for key in ("code", "label", "kind", "api_field", "default_line"):
            assert key in s, f"{s.get('code')} missing {key}"


def test_fouls_bridges_from_api_field_to_code():
    # raw is keyed by api_field (what parse_statistics produces); foul -> 7
    actuals = actuals_from_raw({"fouls": 7}, _MENU)
    assert actuals["foul"] == 7
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_stats_menu.py -q`
Expected: FAIL (menu still contains `save`, no `foul`).

- [ ] **Step 3: Edit the menu**

Replace the contents of `assets/data/stats_menu.json` with:

```json
{
  "_comment": "Predictable stats. kind=incident (count occurrences) or delta (end-minus-start). api_field is the engine field key produced by parse_statistics (see normalize_soccer._STAT_FIELD).",
  "stats": [
    { "code": "goal",   "label": "Goals",           "kind": "incident", "api_field": "goals",        "default_line": 1 },
    { "code": "shot",   "label": "Shots on target", "kind": "delta",    "api_field": "shots_on_goal","default_line": 2 },
    { "code": "corner", "label": "Corners",         "kind": "delta",    "api_field": "corner_kicks", "default_line": 3 },
    { "code": "card",   "label": "Cards",           "kind": "incident", "api_field": "cards",        "default_line": 1 },
    { "code": "foul",   "label": "Fouls",           "kind": "delta",    "api_field": "fouls",        "default_line": 4 }
  ]
}
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS. If any existing test hard-codes `save`/`goalkeeper_saves` as a predictable
stat, update that test to the new menu (search: `.venv/Scripts/python -m pytest tests/ -q -k save`
and grep tests for `"save"`). The demo script in `flow.py:_demo_script` still includes a
`goalkeeper_saves` raw field -- that is harmless (unused now) but remove that key from each
snapshot dict for tidiness.

- [ ] **Step 5: Commit**

```bash
git add assets/data/stats_menu.json tests/test_stats_menu.py
git commit -m "feat: stat menu -> goals/shots/corners/cards/fouls (drop saves)"
```

---

## Task 2: MatchClock pure engine

**Files:**
- Create: `src/game/match_clock.py`
- Test: `tests/test_match_clock.py`

Composes with the existing `HalfClock` (`src/game/half_clock.py`) for window math.

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_clock.py`:

```python
from src.game.half_clock import HalfClock
from src.game.match_clock import MatchClock

# 45-min half, 5-min windows -> 9 regular windows, ET window = 10.
CLOCK = HalfClock(45, 5)
K = 1_000_000.0  # arbitrary kickoff epoch


def mc():
    return MatchClock(kickoff_epoch=K, clock=CLOCK)


def test_before_kickoff_is_minute_zero_window_zero_editing_one():
    m = mc()
    assert m.current_minute(K - 120) == 0
    assert m.playing_window(K - 120) == 0
    assert m.editing_window(K - 120) == 1


def test_at_kickoff_window_one_plays_and_you_edit_two():
    m = mc()
    assert m.current_minute(K) == 0
    assert m.playing_window(K) == 1
    assert m.editing_window(K) == 2


def test_minute_and_windows_advance():
    m = mc()
    assert m.current_minute(K + 5 * 60) == 5
    assert m.playing_window(K + 5 * 60) == 2
    assert m.editing_window(K + 5 * 60) == 3


def test_mid_half_join():
    m = mc()
    assert m.current_minute(K + 23 * 60) == 23
    assert m.playing_window(K + 23 * 60) == 5   # 20-25' window
    assert m.editing_window(K + 23 * 60) == 6


def test_extra_time_window_caps():
    m = mc()
    assert m.playing_window(K + 45 * 60) == 10   # ET window
    assert m.editing_window(K + 45 * 60) == 10   # nothing beyond ET
    assert m.playing_window(K + 60 * 60) == 10   # stays at ET past 45'


def test_windows_entered_at_kickoff():
    m = mc()
    assert m.windows_entered(K - 1, K + 1) == [1]


def test_windows_entered_at_a_boundary():
    m = mc()
    assert m.windows_entered(K + 4 * 60, K + 5 * 60) == [2]


def test_windows_entered_handles_a_focus_loss_skip():
    m = mc()
    # tab backgrounded from 4' (window 1) to 16' (window 4): catch up 2,3,4
    assert m.windows_entered(K + 4 * 60, K + 16 * 60) == [2, 3, 4]


def test_windows_entered_empty_when_no_boundary():
    m = mc()
    assert m.windows_entered(K + 60, K + 90) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_match_clock.py -q`
Expected: FAIL with `ModuleNotFoundError: src.game.match_clock`.

- [ ] **Step 3: Implement**

Create `src/game/match_clock.py`:

```python
# src/game/match_clock.py
"""Pure wall-clock match engine: maps a kickoff time and 'now' to the live match minute
and to which 5-minute window is playing vs. which the player is editing.

No pygame, no I/O, no real clock -- 'now' is passed in (epoch seconds) so it is fully
unit-testable and deterministic. Window numbering and the Extra-Time index come from the
composed HalfClock. The player always edits one window ahead of the one playing
(see the spec's timing table)."""
from dataclasses import dataclass
from src.game.half_clock import HalfClock


@dataclass(frozen=True)
class MatchClock:
    kickoff_epoch: float
    clock: HalfClock

    def current_minute(self, now: float) -> int:
        """Live match minute, clamped at 0 before kickoff. Pure wall-clock -- it keeps
        advancing with no API input."""
        return max(0, int((now - self.kickoff_epoch) // 60))

    def playing_window(self, now: float) -> int:
        """1-based index of the window currently in progress; 0 before kickoff. Caps at the
        Extra-Time window (stoppage keeps the clock past 45')."""
        if now < self.kickoff_epoch:
            return 0
        w = self.current_minute(now) // self.clock.window_minutes + 1
        return min(w, self.clock.extra_time_window)

    def editing_window(self, now: float) -> int:
        """The window the player fills in: one ahead of the playing window, capped at ET
        (while ET plays there is nothing further to edit)."""
        return min(self.playing_window(now) + 1, self.clock.extra_time_window)

    def windows_entered(self, prev_now: float, now: float) -> list[int]:
        """Window indices newly ENTERED in (prev_now, now]. Normally [] or one index at a
        boundary; returns several if a backgrounded tab skipped boundaries. The caller
        locks+resolves each in order. ET is entered by time at 45'; its RESOLUTION is
        status-driven (halftime) and handled by the caller, not here."""
        prev = self.playing_window(prev_now)
        cur = self.playing_window(now)
        return list(range(prev + 1, cur + 1))
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_match_clock.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/game/match_clock.py tests/test_match_clock.py
git commit -m "feat: MatchClock pure wall-clock window engine"
```

---

## Task 3: feed_cache_policy pure helpers

**Files:**
- Create: `src/game/feed_cache_policy.py`
- Test: `tests/test_feed_cache_policy.py`

Pure logic for the warm cache: the storage key, blob (de)serialization, and whether a
restart should poll immediately or rely on the cached snapshot.

- [ ] **Step 1: Write the failing test**

Create `tests/test_feed_cache_policy.py`:

```python
from src.game import feed_cache_policy as p


def test_cache_key_is_normalised_by_username_and_fixture():
    assert p.cache_key("  DrPAJ ", 1539007) == p.cache_key("drpaj", 1539007)
    assert p.cache_key("a", 1) != p.cache_key("a", 2)
    assert p.cache_key("a", 1) != p.cache_key("b", 1)


def test_make_blob_then_round_trip():
    blob = p.make_blob({"fixture": {"x": 1}}, now=100.0)
    assert blob["cached_at"] == 100.0
    assert blob["snapshot"] == {"fixture": {"x": 1}}
    text = p.serialize(blob)
    assert p.deserialize(text) == blob


def test_deserialize_bad_text_is_none():
    assert p.deserialize("not json") is None
    assert p.deserialize(None) is None


def test_should_poll_on_start():
    blob = p.make_blob({}, now=100.0)
    # within poll window -> warm start, no poll
    assert p.should_poll_on_start(blob, now=200.0, poll_seconds=300) is False
    # older than poll window -> poll for fresh data
    assert p.should_poll_on_start(blob, now=500.0, poll_seconds=300) is True
    # no cache at all -> must poll
    assert p.should_poll_on_start(None, now=10.0, poll_seconds=300) is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_feed_cache_policy.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/game/feed_cache_policy.py`:

```python
# src/game/feed_cache_policy.py
"""Pure policy for the client-side warm cache (no I/O here -- src/sync/local_store does that).

On restart the client loads the last relay snapshot it saved so the lineups/score/clock show
instantly and no API call is spent re-learning them. These helpers own the storage key, the
blob format, and the rule for whether a restart still needs a fresh poll."""
import json
from typing import Optional


def cache_key(username: str, fixture_id: int) -> str:
    """Per-user, per-fixture key. Same username (case/space-insensitive) + same fixture maps
    to the same slot, so a restart reuses the cache."""
    return f"predictor:{(username or '').strip().lower()}:{int(fixture_id)}"


def make_blob(snapshot: dict, now: float) -> dict:
    """Wrap a relay snapshot with the wall-clock time it was stored."""
    return {"snapshot": snapshot, "cached_at": float(now)}


def serialize(blob: dict) -> str:
    return json.dumps(blob)


def deserialize(text: Optional[str]) -> Optional[dict]:
    """Parse a stored blob; None on missing/corrupt data (never raises)."""
    if not text:
        return None
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def should_poll_on_start(blob: Optional[dict], now: float, poll_seconds: float) -> bool:
    """True if the client should poll immediately on startup. False only when a cached blob
    is younger than one poll interval (warm start, no API call needed yet)."""
    if not blob or "cached_at" not in blob:
        return True
    return (now - float(blob["cached_at"])) >= poll_seconds
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_feed_cache_policy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/game/feed_cache_policy.py tests/test_feed_cache_policy.py
git commit -m "feat: feed_cache_policy pure warm-cache helpers"
```

---

## Task 4: LocalStore platform persistence

**Files:**
- Create: `src/sync/local_store.py`
- Test: `tests/test_local_store.py`

Mirrors the import-safe pattern in `src/sync/wasm_transport.py`: WASM-only imports happen
lazily inside methods; on desktop it reads/writes a JSON file. Tests cover the desktop path
(the WASM/localStorage path only runs in a browser).

- [ ] **Step 1: Write the failing test**

Create `tests/test_local_store.py`:

```python
from src.sync.local_store import LocalStore


def test_set_then_get_roundtrips_on_desktop(tmp_path):
    store = LocalStore(file_path=tmp_path / "store.json")
    assert store.get("k") is None
    store.set("k", "v")
    assert store.get("k") == "v"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "store.json"
    LocalStore(file_path=path).set("a", "1")
    assert LocalStore(file_path=path).get("a") == "1"


def test_overwrites_key(tmp_path):
    store = LocalStore(file_path=tmp_path / "store.json")
    store.set("a", "1")
    store.set("a", "2")
    assert store.get("a") == "2"


def test_corrupt_file_reads_as_empty(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("not json", encoding="utf-8")
    store = LocalStore(file_path=path)
    assert store.get("a") is None
    store.set("a", "1")          # recovers by overwriting
    assert store.get("a") == "1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_local_store.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/sync/local_store.py`:

```python
# src/sync/local_store.py
"""Persistent key/value storage for the warm cache.

In the browser (pygbag/WASM) this is window.localStorage; on desktop it is a small JSON
file. Import-safe: `platform` is WASM-only and imported lazily, so importing this module on
desktop (and in tests) never touches it. Values are strings (the caller serialises)."""
import json
import sys
from pathlib import Path
from typing import Optional


class LocalStore:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._is_web = sys.platform == "emscripten"
        self._path = Path(file_path) if file_path is not None else None

    def get(self, key: str) -> Optional[str]:
        if self._is_web:
            import platform  # WASM-only
            return platform.window.localStorage.getItem(key)
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        if self._is_web:
            import platform  # WASM-only
            platform.window.localStorage.setItem(key, value)
            return
        data = self._read()
        data[key] = value
        self._write(data)

    # -- desktop JSON-file backend ----------------------------------------
    def _read(self) -> dict:
        if not self._path or not self._path.exists():
            return {}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, data: dict) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_local_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sync/local_store.py tests/test_local_store.py
git commit -m "feat: LocalStore (localStorage / desktop JSON file)"
```

---

## Task 5: Kickoff times in config + zero-API countdown

**Files:**
- Modify: `config/game_config.json` (live.fixtures, new live.kickoffs OR per-fixture kickoff)
- Modify: `src/game/live_feed.py` (seed kickoff_iso from config when not yet polled)
- Test: `tests/test_live_feed.py` (add a case)

Goal: the pre-game countdown reads kickoff time from config, so no API call is spent learning
it. We keep `LiveFeed.kickoff_iso()` as the single source the screen reads, but allow it to be
seeded from config before any poll.

- [ ] **Step 1: Add kickoff timestamps to config**

In `config/game_config.json`, change each entry of `live.fixtures` to carry a `kickoff` ISO
timestamp. Today's first kickoff is known (17:00 UTC); fill the other two from a single
fixtures lookup at implementation time (run `scripts/smoke_test_apifootball.py` or one manual
`?id=` call) -- do not guess. Example shape:

```json
"fixtures": [
  {"id": 1539007, "label": "Netherlands v Sweden",    "kickoff": "2026-06-20T17:00:00+00:00"},
  {"id": 1489393, "label": "Germany v Ivory Coast",   "kickoff": "<from API>"},
  {"id": 1539006, "label": "Turkiye v Paraguay",      "kickoff": "<from API>"}
]
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_live_feed.py`:

```python
from src.game.live_feed import LiveFeed

def test_kickoff_iso_can_be_seeded_before_any_poll():
    feed = LiveFeed()
    assert feed.kickoff_iso() is None
    feed.seed_kickoff("2026-06-20T17:00:00+00:00")
    assert feed.kickoff_iso() == "2026-06-20T17:00:00+00:00"

def test_a_real_poll_overrides_a_seeded_kickoff():
    feed = LiveFeed()
    feed.seed_kickoff("2026-06-20T17:00:00+00:00")
    feed.record({"fixture": {"response": [
        {"fixture": {"date": "2026-06-20T17:05:00+00:00", "status": {"short": "NS"}}}]}})
    assert feed.kickoff_iso() == "2026-06-20T17:05:00+00:00"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_live_feed.py -q -k kickoff`
Expected: FAIL (`seed_kickoff` missing).

- [ ] **Step 4: Implement seed_kickoff**

In `src/game/live_feed.py`, add after `kickoff_iso`:

```python
    def seed_kickoff(self, kickoff_iso: str) -> None:
        """Set the scheduled kickoff from a non-API source (config) so the countdown shows
        with zero API calls. A real poll's fixture.date overrides this (see record())."""
        if kickoff_iso:
            self._kickoff_iso = kickoff_iso
```

(`record()` already overwrites `_kickoff_iso` from `fixture.date` when present, so no further
change is needed there.)

- [ ] **Step 5: Seed from config at flow entry**

In `src/ui/flow.py` `start_live`, after `feed = LiveFeed()`, seed from the chosen fixture's
config entry:

```python
    feed = LiveFeed()
    for fx in (_LIVE.get("fixtures") or []):
        if fx.get("id") == fixture_id and fx.get("kickoff"):
            feed.seed_kickoff(fx["kickoff"])
            break
```

- [ ] **Step 6: Run tests + launch**

Run: `.venv/Scripts/python -m pytest tests/ -q` (expect green)
Run: `.venv/Scripts/python src/main.py` (window opens; quit with the window close button)

- [ ] **Step 7: Commit**

```bash
git add config/game_config.json src/game/live_feed.py src/ui/flow.py tests/test_live_feed.py
git commit -m "feat: kickoff times from config; zero-API pre-game countdown"
```

---

## Task 6: LivePlayScreen -- the unified always-running screen

**Files:**
- Create: `src/ui/screens/live_play_screen.py`
- Modify: `config/layout_config.json` (new `liveplay_*` layout keys -- mirror existing
  `play_*` keys; pick values by copying the analogous `play_*` entry)
- Test: `tests/test_live_play_screen_logic.py` (pure-logic helpers only; pygame rendering is
  exercised by the headless smoke driver in Task 8, not unit-tested)

This screen hosts the whole half. To keep it testable despite living in `src/ui`, put the
clock/lock/resolve DECISIONS in small pure helper methods that take `now` and return data,
and keep pygame strictly in `draw()`. The screen calls back into the flow to resolve windows
(so scoring stays in the engine).

### Interface (the flow constructs it)

```python
LivePlayScreen(
    app,                       # App
    feed,                      # LiveFeed
    feed_client,               # FeedClient
    match_clock,               # MatchClock
    fixture_id,                # int
    editing_window_start,      # int: first window the player may edit (from live_plan)
    on_lock,                   # Callable[[int, list[Prediction], str, bool], WindowReport]
                               #   flow resolves the window, returns the report to show inline
    on_finished,               # Callable[[], None]: half over (API halftime) -> FinalScreen
    poll_seconds,              # float
    available,                 # list[DraftedAthlete] (the drafted hand)
    now_fn=time.time,          # injectable clock for tests
    sim=None,
)
```

`on_lock(window, preds, active_id, use_power) -> WindowReport` is the bridge to the engine:
the flow runs `GameSession.resolve_window` + `build_window_report` and returns the report;
the screen renders that report inline. The screen NEVER imports the engine scoring directly.

### Behaviour (per frame, in `update(dt)`)

1. `now = self.now_fn()`.
2. Wall-clock poll: if `now - self._last_poll_epoch >= poll_seconds` and not already polling,
   fire `asyncio.ensure_future(self._poll())` and set `self._last_poll_epoch = now`. (This is
   the focus-proof poll: on tab resume `now` jumps and it polls at once.)
3. `for w in match_clock.windows_entered(self._last_now, now):` -- for each newly entered
   window `w`: collect the current dials as a locked `Prediction` list for window `w`, call
   `report = on_lock(w, preds, active_id, use_power)` ONLY when `w-1 >= editing_window_start`
   (i.e. there is a real prior window to resolve)... see the precise rule below; then advance
   the editor to the next window and arm the inline reveal with `report`.
4. `self._last_now = now`.
5. If `feed.match_status() == halftime`: resolve the final (ET) window via `on_lock` if not
   already done, then `on_finished()`.

Precise lock/resolve rule for each entered window `w` (matches the spec table):
- The dials currently on screen belong to window `w` (the player was editing it).
- Locking: snapshot the dials into `self._locked[w] = (preds, active_id, use_power)`.
- Resolving: the window that just ended is `w-1`. If `w-1 >= editing_window_start` and
  `w-1` is in `self._locked`, call `report = on_lock(w-1, *self._locked[w-1])` and show it
  inline. (At kickoff, `w=1`, `w-1=0` -> nothing to resolve, just lock W1.)
- Advance editor to `w+1`: reset dials to menu defaults (`s["default_line"]`), clear
  `active_id` selection's lock state (keep the chosen player as a convenience), set the
  editor header to window `w+1`.

### Pure helpers to unit-test

Extract these as module-level pure functions (no pygame) and test them:

```python
def lock_and_resolve_plan(entered: list[int], editing_start: int) -> list[tuple[int, int|None]]:
    """For each newly entered window w, return (lock_window=w, resolve_window=w-1 or None).
    resolve is None when w-1 < editing_start (no prior window the player owned)."""
    out = []
    for w in entered:
        resolve = w - 1 if (w - 1) >= editing_start else None
        out.append((w, resolve))
    return out
```

- [ ] **Step 1: Write the failing test (pure helper)**

Create `tests/test_live_play_screen_logic.py`:

```python
from src.ui.screens.live_play_screen import lock_and_resolve_plan


def test_kickoff_locks_w1_resolves_nothing():
    assert lock_and_resolve_plan([1], editing_start=1) == [(1, None)]


def test_boundary_locks_next_resolves_prev():
    assert lock_and_resolve_plan([2], editing_start=1) == [(2, 1)]


def test_focus_skip_chains_locks_and_resolves():
    assert lock_and_resolve_plan([2, 3, 4], editing_start=1) == [(2, 1), (3, 2), (4, 3)]


def test_mid_half_join_does_not_resolve_unowned_window():
    # joined editing window 6; entering 6 must not try to resolve window 5
    assert lock_and_resolve_plan([6], editing_start=6) == [(6, None)]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_live_play_screen_logic.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the screen**

Create `src/ui/screens/live_play_screen.py`. Use `src/ui/screens/play_screen.py` as the
template for the dial rows, the player picker, the scroll viewport, and the report rendering
(copy those helpers; they already fit a 414x896 canvas). Use
`src/ui/screens/live_wait_screen.py` as the template for `_poll()` and the kickoff-countdown
lobby. Put `lock_and_resolve_plan` at module level (above the class). Skeleton:

```python
# src/ui/screens/live_play_screen.py
"""The unified live screen: one screen for the whole half. A wall-clock MatchClock drives a
running match clock; the player always edits the NEXT window's dials while the current window
plays out. At each window boundary the dials auto-lock, the just-finished window resolves
inline (meters tick, banner, report), and the editor advances. Polling is wall-clock anchored
so losing browser focus never strands the feed; a force-update button polls on demand.

All pygame is in this file; scoring stays in the engine (reached via the on_lock callback).
The lock/resolve DECISION is the pure module-level lock_and_resolve_plan() so it is testable.
"""
import asyncio
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, ScrollButtons, athlete_card, font
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.game.match_clock import MatchClock
from src.game.live_feed import LiveFeed
from src.game.window_report import WindowReport
from src.game.kickoff import (seconds_to_kickoff, kickoff_phase, format_minutes,
                              PHASE_ACTIVE)
from src.sync.feed_client import FeedClient
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_HALFTIME = CONFIG["feed"]["halftime_status"]
_WARN_S = CONFIG["live"]["warn_minutes_before"] * 60
_START_S = CONFIG["live"]["start_minutes_before"] * 60


def lock_and_resolve_plan(entered: list[int], editing_start: int) -> list:
    """For each newly entered window w: (lock=w, resolve=w-1 or None when w-1<editing_start)."""
    out = []
    for w in entered:
        resolve = w - 1 if (w - 1) >= editing_start else None
        out.append((w, resolve))
    return out


class LivePlayScreen(Screen):
    def __init__(self, app, feed, feed_client, match_clock, fixture_id,
                 editing_window_start, on_lock, on_finished, poll_seconds,
                 available, now_fn=time.time, sim=None) -> None:
        super().__init__(app)
        self.feed = feed
        self.feed_client = feed_client
        self.mc = match_clock
        self.fixture_id = fixture_id
        self.editing_start = editing_window_start
        self.on_lock = on_lock
        self.on_finished = on_finished
        self.poll_seconds = poll_seconds
        self.available = available
        self.now_fn = now_fn
        self.sim = sim
        # editor state for the window currently being filled in
        self.editing_window = editing_window_start
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self.active_id: Optional[str] = None
        self.use_power = False
        self._locked: dict[int, tuple] = {}        # window -> (preds, active_id, use_power)
        self.last_report: Optional[WindowReport] = None
        self.feedback = ""
        # timing/poll bookkeeping (wall clock)
        now = self.now_fn()
        self._last_now = now
        self._last_poll_epoch = now - poll_seconds   # poll soon after open (gated by phase)
        self._polling = False
        self._finished = False
        # buttons: force-update + the existing scroll/picker plumbing from PlayScreen
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.update_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("liveplay_update_btn_h", 48) - 12,
                        sw - 2 * m, LAYOUT.i("liveplay_update_btn_h", 48)),
            "Update now")

    # -- pure-ish editor helpers --
    def _current_preds(self) -> list[Prediction]:
        return [Prediction(s["code"], self.lines[s["code"]]) for s in _STATS]

    def _advance_editor(self, to_window: int) -> None:
        self.editing_window = to_window
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        # keep self.active_id as a convenience default for the next window

    # -- polling (wall clock) --
    async def _poll(self) -> None:
        try:
            snap = await self.feed_client.get_feed(self.fixture_id)
            self.feed.record(snap)
            self.feedback = ""
        except Exception as exc:
            self.feedback = f"reconnecting ({type(exc).__name__})"
        finally:
            self._polling = False

    def _phase(self, now: float) -> str:
        secs = seconds_to_kickoff(self.feed.kickoff_iso(), now)
        return kickoff_phase(secs, self.feed.match_status(), _WARN_S, _START_S)

    def _maybe_poll(self, now: float, force: bool = False) -> None:
        if self._polling:
            return
        due = (now - self._last_poll_epoch) >= self.poll_seconds
        # Pre-kickoff quota discipline: do not poll until within the start window.
        if not force and self._phase(now) != PHASE_ACTIVE:
            return
        if force or due:
            self._polling = True
            self._last_poll_epoch = now
            asyncio.ensure_future(self._poll())

    # -- frame update --
    def update(self, dt: float) -> None:
        if self._finished:
            return
        now = self.now_fn()
        self._maybe_poll(now)
        entered = self.mc.windows_entered(self._last_now, now)
        for lock_w, resolve_w in lock_and_resolve_plan(entered, self.editing_start):
            self._locked[lock_w] = (self._current_preds(), self.active_id, self.use_power)
            if resolve_w is not None and resolve_w in self._locked:
                preds, aid, pw = self._locked[resolve_w]
                if aid:
                    self.last_report = self.on_lock(resolve_w, preds, aid, pw)
            self._advance_editor(lock_w + 1)
        self._last_now = now
        if self.feed.match_status() == _HALFTIME and not self._finished:
            self._finished = True
            self.on_finished()

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and self.update_btn.hit(event.pos):
            self._maybe_poll(self.now_fn(), force=True)
            return
        # dial +/- and player taps: copy the corresponding branches from PlayScreen.handle
        # (stat row -> adjust self.lines[code]; player row -> set self.active_id).
        ...

    # -- draw --
    def draw(self, surface: pygame.Surface) -> None:
        # Header: wall-clock minute + score + status. Use feed.current_minute() ONLY as a
        # fallback; the live clock is self.mc.current_minute(self.now_fn()).
        # Lobby (pre-kickoff): if self._phase(now) != PHASE_ACTIVE, draw the countdown
        #   ("Kickoff in N min") and the W1 editor; copy from live_wait_screen._draw_pregame.
        # Active: draw the editor dials + player picker (copy PlayScreen._draw_stats/_players),
        #   the predictions panel (locked windows, newest first, line number above each code),
        #   the inline reveal of self.last_report (copy PlayScreen._draw_report), and the
        #   "Update now" button.
        ...
```

Fill the three `...` blocks by copying and adapting the matching code from
`play_screen.py` (dials, player picker, report panel) and `live_wait_screen.py` (countdown).
Keep all sizes/positions in `config/layout_config.json` under `liveplay_*` keys.

- [ ] **Step 4: Run the logic test**

Run: `.venv/Scripts/python -m pytest tests/test_live_play_screen_logic.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite + launch**

Run: `.venv/Scripts/python -m pytest tests/ -q` (green)
Run: `.venv/Scripts/python src/main.py` (window opens)

- [ ] **Step 6: Commit**

```bash
git add src/ui/screens/live_play_screen.py config/layout_config.json tests/test_live_play_screen_logic.py
git commit -m "feat: LivePlayScreen unified always-running live screen"
```

---

## Task 7: Rewrite LiveFlow to host the one screen + warm cache

**Files:**
- Modify: `src/ui/flow.py` (`LiveFlow`, `start_live`)
- Test: extend `TOOLS/smoke_flow.py` is covered in Task 8; here add a focused flow test in
  `tests/test_live_flow_lock.py`

`LiveFlow` no longer does predict -> wait -> resolve per window. It builds the `MatchClock`,
constructs `LivePlayScreen`, and provides the `on_lock` callback that runs the engine and
returns a `WindowReport`. It also wires the warm cache: load on entry, save on each poll.

### on_lock callback (the engine bridge)

```python
    def _on_lock(self, window, preds, active_id, use_power):
        actuals = self._window_actuals_for(window)
        s_before = self.session.success_meter.value
        c_before = self.session.concede_meter.value
        res = self.session.resolve_window(window=window, predictions=preds,
                                          active_id=active_id, use_power=use_power,
                                          actuals=actuals)
        for ev in res.score_events:
            self.score_codes.append(ev.to_code())
        report = build_window_report(
            window=window, predictions=preds, actuals=actuals,
            stat_labels=_STAT_LABELS,
            success_value=self.session.success_meter.value,
            concede_value=self.session.concede_meter.value,
            success_threshold=_THRESH, concede_threshold=_THRESH_C,
            success_fired=res.success_fired, concede_fired=res.concede_fired,
            success_shot=res.success_shot, concede_shot=res.concede_shot)
        return report
```

`_window_actuals_for(window)` is the existing `LiveFlow._window_actuals` logic generalised to
take a window arg (start = clock.window_start(window); end = window_end or last_known_minute
for ET).

### Warm cache wiring (in start_live)

```python
    from src.sync.local_store import LocalStore
    from src.game import feed_cache_policy as cachep
    store = LocalStore()                       # localStorage on web, no file on web
    key = cachep.cache_key(username, fixture_id)
    blob = cachep.deserialize(store.get(key))
    if blob:
        feed.record(blob["snapshot"])          # warm display instantly, no API call
```

On each successful poll, the screen's `_poll` (or a flow hook passed in) writes:
`store.set(key, cachep.serialize(cachep.make_blob(snapshot, now)))`. Pass `store`, `key`, and
`now_fn` into the screen so `_poll` can persist; OR have `on_lock`/a `on_snapshot` callback do
it. Simplest: give `LivePlayScreen._poll` an optional `on_snapshot(snapshot)` callback that
the flow sets to the cache-write. `username` reaches `start_live` via a new parameter threaded
from `start_app -> start_launcher -> start_live_select -> start_live` (it already threads
`is_lead`; thread `username` the same way).

- [ ] **Step 1: Write the failing flow test**

Create `tests/test_live_flow_lock.py`. This drives the engine bridge without pygame by
calling the flow's `_on_lock` directly with a stub feed. (Construct `LiveFlow` with a fake
`app` that records `set_screen`, a `LiveFeed` seeded with two snapshots, a real `MatchClock`,
and a drafted roster; assert `_on_lock(1, preds, active_id, False)` returns a `WindowReport`
with the expected per-stat results.) Use the existing `tests/test_window_report.py` and
`tests/test_live_feed.py` as references for building snapshots and rosters.

```python
# Skeleton -- fill feed snapshots and roster from the referenced tests.
def test_on_lock_returns_a_window_report_and_scores():
    flow = _make_live_flow_with_two_snapshots()   # helper built per references above
    report = flow._on_lock(1, [Prediction("shot", 1)], flow.session.roster.available()[0].athlete_id, False)
    assert report.window == 1
    assert any(r.label == "Shots on target" for r in report.results)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_live_flow_lock.py -q`
Expected: FAIL (`_on_lock` not defined / LiveFlow signature changed).

- [ ] **Step 3: Implement the LiveFlow rewrite**

Rewrite `LiveFlow` in `src/ui/flow.py`:
- Drop `_after_predict`/`_after_cinematic`/`_play_window` overrides that staged separate
  screens.
- In `_after_draft`: build `MatchClock(kickoff_epoch, HalfClock(_HALF_MIN, _WINDOW_MIN))`
  where `kickoff_epoch` comes from `seconds_to_kickoff`/the seeded kickoff (compute
  `kickoff_epoch = now + seconds_to_kickoff(feed.kickoff_iso(), now)`; if None, use `now`
  so a match already live treats "now" as kickoff baseline -- acceptable for v1 single half).
  Determine `editing_window_start` from `live_plan(...)` (first remaining scored window).
  Construct `LivePlayScreen(...)` with `on_lock=self._on_lock`,
  `on_finished=self._to_final`, and the drafted `available`.
- Add `_on_lock` (above) and `_window_actuals_for(window)`.
- Add `_to_final`: `team, opp = aggregate(self.score_codes); app.set_screen(FinalScreen(...))`.

Thread `username` through `start_app -> start_launcher -> start_live_select -> start_live` and
into `LiveFlow`; wire the warm cache load/save as above.

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_live_flow_lock.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + launch**

Run: `.venv/Scripts/python -m pytest tests/ -q` (green)
Run: `.venv/Scripts/python src/main.py`

- [ ] **Step 6: Commit**

```bash
git add src/ui/flow.py tests/test_live_flow_lock.py
git commit -m "feat: LiveFlow hosts the unified live screen; warm cache wiring"
```

---

## Task 8: Headless integration smoke + cleanup

**Files:**
- Modify: `TOOLS/smoke_flow.py` (add a live-screen drive with an injected clock)
- Modify: `src/ui/screens/live_wait_screen.py` (remove the temporary diagnostic line from the
  last debugging session now that the feed path is proven; keep the screen for the
  lineup-wait lobby ONLY if still used, else delete and remove its import in flow.py)

- [ ] **Step 1: Drive the live screen headlessly**

Extend `TOOLS/smoke_flow.py` to: build a `LiveFeed` with a scripted set of snapshots (reuse
`_demo_script` stats), a `MatchClock` with `kickoff_epoch = 0`, and a `now_fn` the driver
advances manually (e.g. step `now` by 60s per loop), then tick `LivePlayScreen.update(dt)` and
assert it locks/resolves each window and ultimately calls `on_finished`. This proves the
boundary logic end-to-end with no pygame event loop and no network.

- [ ] **Step 2: Run the smoke driver**

Run: `.venv/Scripts/python TOOLS/smoke_flow.py`
Expected: prints OK for the live path reaching the final screen (ASCII output only).

- [ ] **Step 3: Remove debugging cruft**

Delete the diagnostic block (transport name / poll count / busy) added to
`live_wait_screen.py` during the fetch-hang debugging. If `LiveWaitScreen` is no longer
referenced by `flow.py` (the lobby moved into `LivePlayScreen`), delete the file and its
import; otherwise keep only the lineup-wait lobby role.

- [ ] **Step 4: Full suite + launch + web build sanity**

Run: `.venv/Scripts/python -m pytest tests/ -q` (all green; >= 125 + new tests)
Run: `.venv/Scripts/python src/main.py`
Run: `.venv/Scripts/python TOOLS/build_web_mobile.py --build-only` (build succeeds)

- [ ] **Step 5: Commit + log**

```bash
git add TOOLS/smoke_flow.py src/ui/screens/live_wait_screen.py src/ui/flow.py log.md
git commit -m "test: headless live-screen smoke; remove fetch-debug cruft"
```

Append to `log.md`:
`2026-06-20 | Live loop redesign: MatchClock + LivePlayScreen (predict-ahead, auto-lock, inline reveal), feed_cache_policy + LocalStore warm cache, config kickoff times, stat menu -> fouls (drop saves) | src/game/match_clock.py src/game/feed_cache_policy.py src/sync/local_store.py src/ui/screens/live_play_screen.py src/ui/flow.py assets/data/stats_menu.json config/`

---

## Deferred to a follow-up (do NOT do here)

- Rebuild + mirror into `WEB_BUILD/PREDICTOR/` + repackage `PREDICTOR_deploy.zip` (deploy
  step -- do after the user reviews the new live screen locally).
- Sub-project C: dynamic upcoming-match picker (own spec).
- The 414x896 desktop/mobile aspect-ratio web-layout fix (own small task).

---

## Self-review notes (author)

- Spec section 1 (timing) -> Tasks 2, 6. Section 2 (engine/poll) -> Tasks 2, 6. Section 3
  (screen/panel/force-update/reveal) -> Task 6. Section 4 (stats) -> Task 1. Section 5
  (quota/persistence) -> Tasks 3, 4, 5, 7. Section 6 (files/tests) -> all. No gaps.
- Names are consistent across tasks: `MatchClock.windows_entered`, `lock_and_resolve_plan`,
  `cache_key/make_blob/serialize/deserialize/should_poll_on_start`, `LocalStore.get/set`,
  `LiveFeed.seed_kickoff`, `LivePlayScreen(on_lock,on_finished)`, `LiveFlow._on_lock`.
- The pygame screen body (Task 6 Step 3) is specified by interface + behaviour + which
  existing methods to copy rather than full transcribed pygame, because it is a mechanical
  port of `play_screen.py`/`live_wait_screen.py` rendering; the testable DECISIONS are pure
  and fully coded. This is the one intentional non-verbatim section.
```
