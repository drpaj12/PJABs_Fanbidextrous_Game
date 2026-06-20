# Both-Halves Live Play Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Live play support both halves of a soccer match, auto-selected by join time, each as a separate game, with an API-derived self-correcting second-half clock and a persistent on-screen label of which half you are in.

**Architecture:** Pure join-decision (`half_picker`) and clock math (`HalfClock.start_minute`, `MatchClock.realign`/`display_minute`) live in `src/game/` and are unit-tested. `src/ui/flow.py` wires the decision into the screen sequence; `LivePlayScreen`/`LiveWaitScreen` get half-aware UI and re-alignment. All constants in `config/game_config.json`.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), pytest, pygame-ce (UI only). Spec: `docs/superpowers/specs/2026-06-20-both-halves-design.md`.

**Conventions (every task):**
- Run tests with `.venv/Scripts/python -m pytest tests/ -q`.
- ASCII-only in all `print`/log/`.md` output (`OK`/`FAIL`, `->`, no unicode). pygame surface strings may be unicode.
- Type hints on every function signature. No globals. No magic numbers (config only).
- After each task: append one line to `log.md` as `YYYY-MM-DD | [what] | [files]`, then `git add` + commit (main branch, no branches). End commit messages with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

- Create: `src/game/half_picker.py` -- pure join decision (which half / wait / none).
- Create: `tests/test_half_picker.py`.
- Modify: `src/game/half_clock.py` -- add `start_minute` offset.
- Modify: `tests/test_half_clock.py` -- offset tests.
- Modify: `src/game/match_clock.py` -- add `realign` + `display_minute`.
- Modify: `tests/test_match_clock.py` -- realign/display tests.
- Modify: `src/ui/screens/live_play_screen.py` -- `windows_to_enter` helper, high-water mark, half label, display minute, re-align wiring.
- Modify: `tests/test_live_play_screen_logic.py` -- `windows_to_enter` tests.
- Modify: `src/ui/screens/live_wait_screen.py` -- `wait_for_second_half` mode.
- Modify: `src/ui/flow.py` -- half-aware `LiveFlow`, rewired `start_live`.
- Modify: `tests/test_live_schedule.py` -- 2H half-relative `live_plan` test.
- Modify: `config/game_config.json` -- new live/game keys.
- Modify: `TOOLS/smoke_flow.py` -- `live_smoke_2h()`.

---

## Task 1: Config keys

**Files:**
- Modify: `config/game_config.json`

- [ ] **Step 1: Add the four keys**

In the `live` object add (keep existing keys):
```json
"join_cutoff_minute": 22,
"resync_threshold_seconds": 30,
```
In the `game` object add (keep existing keys):
```json
"second_half_label": "Second Half",
"fulltime_label": "Full Time"
```
(Ensure valid JSON: commas between keys, no trailing comma.)

- [ ] **Step 2: Verify it loads**

Run: `.venv/Scripts/python -c "from src.utils.constants import CONFIG; print('OK', CONFIG['live']['join_cutoff_minute'], CONFIG['live']['resync_threshold_seconds'], CONFIG['game']['second_half_label'], CONFIG['game']['fulltime_label'])"`
Expected: `OK 22 30 Second Half Full Time`

- [ ] **Step 3: Commit**

```bash
git add config/game_config.json
git commit -m "config: add both-halves keys (join_cutoff, resync_threshold, 2H/FT labels)"
```

---

## Task 2: HalfClock.start_minute

**Files:**
- Modify: `src/game/half_clock.py`
- Test: `tests/test_half_clock.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_half_clock.py` (create the file if it does not exist, importing `from src.game.half_clock import HalfClock`):
```python
def test_first_half_offset_is_zero_by_default() -> None:
    c = HalfClock(45, 5)
    assert c.start_minute == 0
    assert c.window_start(1) == 0
    assert c.window_end(1) == 5
    assert c.window_end(9) == 45

def test_second_half_offsets_to_absolute_minutes() -> None:
    c = HalfClock(45, 5, start_minute=45)
    assert c.window_start(1) == 45
    assert c.window_end(1) == 50
    assert c.window_end(9) == 90

def test_second_half_extra_time_starts_at_ninety() -> None:
    c = HalfClock(45, 5, start_minute=45)
    assert c.window_start(c.extra_time_window) == 90
    assert c.regular_windows == 9
    assert c.extra_time_window == 10
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_half_clock.py -q`
Expected: FAIL (TypeError: unexpected keyword `start_minute`, or attribute missing).

- [ ] **Step 3: Implement the offset**

In `src/game/half_clock.py`, add the field and apply it. The dataclass becomes:
```python
@dataclass(frozen=True)
class HalfClock:
    half_minutes: int
    window_minutes: int
    start_minute: int = 0   # 0 for the first half, 45 for the second (absolute match minutes)
```
Change the two boundary methods to add the offset:
```python
    def window_start(self, window: int) -> int:
        """First (absolute) match minute of a window. Valid for regular and ET windows."""
        return self.start_minute + (window - 1) * self.window_minutes

    def window_end(self, window: int) -> int:
        """Last (absolute) match minute of a REGULAR window. Meaningless for ET."""
        return self.start_minute + window * self.window_minutes
```
Leave `regular_windows`, `extra_time_window`, `is_extra_time`, `is_half_over` unchanged. Update the module docstring's last paragraph to note window_start/end are absolute match minutes (offset by `start_minute`).

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_half_clock.py tests/test_live_schedule.py tests/test_match_clock.py -q`
Expected: PASS (existing 1H tests unaffected since default offset is 0).

- [ ] **Step 5: Full suite + commit**

```bash
.venv/Scripts/python -m pytest tests/ -q
git add src/game/half_clock.py tests/test_half_clock.py
git commit -m "feat(half_clock): add start_minute offset for absolute match minutes"
```

---

## Task 3: MatchClock.realign + display_minute

**Files:**
- Modify: `src/game/match_clock.py`
- Test: `tests/test_match_clock.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_match_clock.py` (import `from src.game.match_clock import MatchClock` and `from src.game.half_clock import HalfClock`):
```python
def test_display_minute_adds_half_offset() -> None:
    c = HalfClock(45, 5, start_minute=45)
    mc = MatchClock(kickoff_epoch=1000.0, clock=c)
    # 7 minutes into the half -> display minute 52
    assert mc.current_minute(1000.0 + 7 * 60) == 7
    assert mc.display_minute(1000.0 + 7 * 60) == 52

def test_realign_noop_within_threshold() -> None:
    c = HalfClock(45, 5)
    mc = MatchClock(kickoff_epoch=1000.0, clock=c)
    now = 1000.0 + 10 * 60 + 20      # our elapsed 620s; API minute 10 -> api_elapsed 630s
    assert mc.realign(api_minute_in_half=10, now=now, threshold_seconds=30) is mc

def test_realign_snaps_when_drifted() -> None:
    c = HalfClock(45, 5)
    mc = MatchClock(kickoff_epoch=1000.0, clock=c)
    now = 1000.0 + 5 * 60            # our clock says minute 5...
    snapped = mc.realign(api_minute_in_half=10, now=now, threshold_seconds=30)  # ...API says 10
    assert snapped is not mc
    assert snapped.current_minute(now) == 10

def test_realign_backward_snap() -> None:
    c = HalfClock(45, 5)
    mc = MatchClock(kickoff_epoch=1000.0, clock=c)
    now = 1000.0 + 20 * 60           # our clock says minute 20...
    snapped = mc.realign(api_minute_in_half=12, now=now, threshold_seconds=30)  # ...API says 12
    assert snapped.current_minute(now) == 12
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_match_clock.py -q`
Expected: FAIL (no `display_minute` / `realign`).

- [ ] **Step 3: Implement**

In `src/game/match_clock.py`, add two methods to `MatchClock`:
```python
    def display_minute(self, now: float) -> int:
        """Absolute match minute for display (offsets current_minute by the half's
        start_minute), so the second half reads 46'-90' instead of 1'-45'."""
        return self.clock.start_minute + self.current_minute(now)

    def realign(self, api_minute_in_half: int, now: float,
                threshold_seconds: float) -> "MatchClock":
        """Snap the wall-clock anchor to the API's reported minute when our estimate has
        drifted past threshold_seconds; otherwise return self unchanged. The initial
        anchor (config kickoff for 1H, an estimate for 2H) self-corrects each poll.

        api_minute_in_half is the API match minute mapped into this half (0-based:
        max(0, api_elapsed - clock.start_minute)). We compare against the MIDPOINT of that
        integer minute so a clock sitting mid-minute is not treated as drifted."""
        our_elapsed = now - self.kickoff_epoch
        api_elapsed = (api_minute_in_half + 0.5) * 60
        if abs(our_elapsed - api_elapsed) > threshold_seconds:
            return MatchClock(now - api_elapsed, self.clock)
        return self
```
(`current_minute`, `playing_window`, `editing_window`, `windows_entered` unchanged.)

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_match_clock.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

```bash
.venv/Scripts/python -m pytest tests/ -q
git add src/game/match_clock.py tests/test_match_clock.py
git commit -m "feat(match_clock): add display_minute and self-correcting realign"
```

---

## Task 4: half_picker (join decision)

**Files:**
- Create: `src/game/half_picker.py`
- Test: `tests/test_half_picker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_half_picker.py`:
```python
from src.game.half_picker import pick_half, HalfChoice

H = 45        # half_minutes
CUT = 22      # join_cutoff_minute (half-relative)

def call(status, elapsed):
    return pick_half(status, elapsed, half_minutes=H, join_cutoff_minute=CUT)

def test_prematch_plays_first_half():
    assert call("NS", 0) == HalfChoice(1, False)
    assert call("TBD", 0) == HalfChoice(1, False)

def test_first_half_before_cutoff_plays_first():
    assert call("1H", 0) == HalfChoice(1, False)
    assert call("1H", 21) == HalfChoice(1, False)

def test_first_half_at_or_after_cutoff_waits_for_second():
    assert call("1H", 22) == HalfChoice(2, True)
    assert call("1H", 40) == HalfChoice(2, True)

def test_halftime_waits_for_second():
    assert call("HT", 45) == HalfChoice(2, True)

def test_second_half_before_cutoff_plays_second():
    assert call("2H", 46) == HalfChoice(2, False)   # 46-45=1 < 22
    assert call("2H", 66) == HalfChoice(2, False)   # 66-45=21 < 22

def test_second_half_at_or_after_cutoff_has_no_half_left():
    assert call("2H", 67) == HalfChoice(None, False)  # 67-45=22 >= 22
    assert call("2H", 85) == HalfChoice(None, False)

def test_extra_time_and_breaks_have_no_half_left():
    assert call("ET", 95) == HalfChoice(None, False)
    assert call("BT", 91) == HalfChoice(None, False)
    assert call("P", 120) == HalfChoice(None, False)

def test_finished_has_no_half_left():
    for s in ("FT", "AET", "PEN", "ABD", "AWD", "WO", "CANC"):
        assert call(s, 90) == HalfChoice(None, False)

def test_unknown_status_defaults_to_no_half():
    assert call("???", 10) == HalfChoice(None, False)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_half_picker.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

Create `src/game/half_picker.py`:
```python
# src/game/half_picker.py
"""Pure join-time decision: which half does a player entering NOW play?

Uses the RAW API-Football status short code (not the engine-mapped status) because the
decision must distinguish 1H / HT / 2H / FT, which the mapped vocabulary
(live / halftime / finished) collapses. No pygame, no I/O -- fully unit-testable.

See docs/superpowers/specs/2026-06-20-both-halves-design.md (section A)."""
from dataclasses import dataclass
from typing import Optional

_PREMATCH = {"NS", "TBD", "PST"}
_FIRST_HALF = "1H"
_HALFTIME = "HT"
_SECOND_HALF = "2H"


@dataclass(frozen=True)
class HalfChoice:
    half: Optional[int]   # 1, 2, or None when no playable half remains
    needs_wait: bool      # True when half == 2 but the 2H has not kicked off yet


def pick_half(status_short: str, elapsed: int, half_minutes: int,
              join_cutoff_minute: int) -> HalfChoice:
    """Decide the half to join. `elapsed` is the API match minute (1-90+);
    `join_cutoff_minute` is half-relative (e.g. 22)."""
    s = (status_short or "").upper()

    if s in _PREMATCH:
        return HalfChoice(1, False)

    if s == _FIRST_HALF:
        if elapsed < join_cutoff_minute:
            return HalfChoice(1, False)
        return HalfChoice(2, True)          # too late for 1H -> wait for 2H

    if s == _HALFTIME:
        return HalfChoice(2, True)

    if s == _SECOND_HALF:
        in_half = elapsed - half_minutes
        if in_half < join_cutoff_minute:
            return HalfChoice(2, False)
        return HalfChoice(None, False)      # too late for 2H -> no half left

    # Extra time, breaks, penalties, finished, and anything unknown: no regular half left.
    return HalfChoice(None, False)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_half_picker.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

```bash
.venv/Scripts/python -m pytest tests/ -q
git add src/game/half_picker.py tests/test_half_picker.py
git commit -m "feat(half_picker): pure join-time half selection"
```

---

## Task 5: LivePlayScreen -- high-water windows, half label, display minute, re-align

**Files:**
- Modify: `src/ui/screens/live_play_screen.py`
- Test: `tests/test_live_play_screen_logic.py`

- [ ] **Step 1: Write failing tests for the new pure helper**

Add to `tests/test_live_play_screen_logic.py` (extend the existing import line to also import `windows_to_enter`):
```python
from src.ui.screens.live_play_screen import lock_and_resolve_plan, windows_ready, windows_to_enter


def test_windows_to_enter_forward_progress() -> None:
    assert windows_to_enter(max_entered=0, playing_window=1) == [1]
    assert windows_to_enter(max_entered=3, playing_window=4) == [4]


def test_windows_to_enter_catches_up_skipped_windows() -> None:
    # backgrounded across several boundaries: catch up all of them at once
    assert windows_to_enter(max_entered=2, playing_window=5) == [3, 4, 5]


def test_windows_to_enter_backward_realign_yields_nothing() -> None:
    # a backward clock correction (playing_window < high-water) must not re-enter
    assert windows_to_enter(max_entered=6, playing_window=4) == []
    assert windows_to_enter(max_entered=4, playing_window=4) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_live_play_screen_logic.py -q`
Expected: FAIL (cannot import `windows_to_enter`).

- [ ] **Step 3: Add the pure helper**

In `src/ui/screens/live_play_screen.py`, add next to `windows_ready` / `lock_and_resolve_plan`:
```python
def windows_to_enter(max_entered: int, playing_window: int) -> list[int]:
    """Window indices to lock this frame, using a monotonic high-water mark instead of a
    frame delta. Forward progress (incl. catch-up after a backgrounded tab) returns the new
    indices; a backward clock correction from re-alignment returns [] so an already-played
    window is never re-locked."""
    return list(range(max_entered + 1, playing_window + 1))
```

- [ ] **Step 4: Run helper tests**

Run: `.venv/Scripts/python -m pytest tests/test_live_play_screen_logic.py -q`
Expected: PASS.

- [ ] **Step 5: Wire the constructor for the new params + high-water state**

In `LivePlayScreen.__init__`, add two parameters (place `half_label` and
`resync_threshold_seconds` after `available` and before `now_fn` so existing positional
callers via keywords keep working -- all call sites pass by keyword):
```python
                 available: list[DraftedAthlete],
                 half_label: str = "",
                 resync_threshold_seconds: float = 30.0,
                 now_fn: Callable[[], float] = time.time,
```
Store them and replace the `self._last_now` tracking with a high-water mark. Change the
existing lines:
```python
        now = self.now_fn()
        self._last_now = now
```
to:
```python
        self.half_label = half_label
        self._resync_threshold = resync_threshold_seconds
        now = self.now_fn()
        # High-water mark of the highest playing window entered so far (re-align safe).
        self._max_entered = editing_window_start - 1
```
Add the live-status constant near the other module constants (top of file):
```python
_LIVE_STATUS = "live"
```

- [ ] **Step 6: Re-align + high-water in update()**

In `update()`, replace the window-entry block. The current code is:
```python
        # Lock each newly-entered window and queue the one before it for resolution.
        for lock_w, resolve_w in lock_and_resolve_plan(
                self.mc.windows_entered(self._last_now, now), self.editing_start):
            self._lock_window(lock_w)
            if (resolve_w is not None and resolve_w in self._locked
                    and self._locked[resolve_w][1]):
                self._pending_resolve.add(resolve_w)
            self.edit_window = lock_w + 1
            self._reset_editor()
        self._last_now = now
```
Replace it with:
```python
        # Re-align the wall clock to the API minute when our estimate has drifted; the
        # second-half anchor starts as an estimate and the first-half anchor can lag too.
        if self.feed.match_status() == _LIVE_STATUS and self.feed.current_minute() > 0:
            api_in_half = max(0, self.feed.current_minute() - self.mc.clock.start_minute)
            self.mc = self.mc.realign(api_in_half, now, self._resync_threshold)

        # Lock each newly-entered window (high-water mark) and queue the one before it.
        cur = self.mc.playing_window(now)
        for lock_w, resolve_w in lock_and_resolve_plan(
                windows_to_enter(self._max_entered, cur), self.editing_start):
            self._lock_window(lock_w)
            if (resolve_w is not None and resolve_w in self._locked
                    and self._locked[resolve_w][1]):
                self._pending_resolve.add(resolve_w)
            self.edit_window = lock_w + 1
            self._reset_editor()
        self._max_entered = max(self._max_entered, cur)
```

- [ ] **Step 7: Header -- persistent half label + absolute display minute**

In `draw()`, change the clock render to the absolute display minute and add the half label.
Current:
```python
        cf = font(LAYOUT.i("liveplay_clock_size", 30))
        surface.blit(cf.render(f"{self.mc.current_minute(now)}'", True, _C["accent"]),
                     (m, LAYOUT.i("liveplay_clock_y", 44)))
```
Replace the render call's minute with `self.mc.display_minute(now)`:
```python
        cf = font(LAYOUT.i("liveplay_clock_size", 30))
        surface.blit(cf.render(f"{self.mc.display_minute(now)}'", True, _C["accent"]),
                     (m, LAYOUT.i("liveplay_clock_y", 44)))
```
And draw the half label persistently. Replace the header line block:
```python
        hf = font(LAYOUT.i("liveplay_header_size", 20))
        header = f"Editing window {self.edit_window}"
        surface.blit(hf.render(header, True, _C["text_dim"]),
                     (m, LAYOUT.i("liveplay_header_y", 16)))
```
with:
```python
        hf = font(LAYOUT.i("liveplay_header_size", 20))
        header = (f"{self.half_label}  -  Editing window {self.edit_window}"
                  if self.half_label else f"Editing window {self.edit_window}")
        surface.blit(hf.render(header, True, _C["accent"]),
                     (m, LAYOUT.i("liveplay_header_y", 16)))
```

- [ ] **Step 8: Run the logic suite + full suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (the screen's pure logic tests + everything else; `windows_entered` on
MatchClock is untouched so its tests still pass).

- [ ] **Step 9: Verify the game still launches**

Run: `.venv/Scripts/python src/main.py` (close the window after it opens).
Expected: launches with no traceback.

- [ ] **Step 10: Commit**

```bash
git add src/ui/screens/live_play_screen.py tests/test_live_play_screen_logic.py
git commit -m "feat(live_play): half label, absolute minute, re-align, high-water windows"
```

---

## Task 6: LiveWaitScreen -- wait_for_second_half mode

**Files:**
- Modify: `src/ui/screens/live_wait_screen.py`

- [ ] **Step 1: Add the parameter**

In `LiveWaitScreen.__init__`, add `wait_for_second_half: bool = False` after
`wait_for_lineups`, and store `self.wait_for_second_half = wait_for_second_half`.

- [ ] **Step 2: Readiness branch**

In `_is_ready`, add a branch at the top (after computing `status`):
```python
    def _is_ready(self) -> bool:
        status = self.feed.match_status()
        if self.wait_for_second_half:
            return (self.feed.status_short().upper() == "2H"
                    or status == _FINISHED_STATUS)
        if self.wait_for_lineups:
            return self.feed.has_lineups()
        half_over = status in (_HALFTIME_STATUS, _FINISHED_STATUS)
        if self.target_minute is None:
            return half_over
        return half_over or self.feed.current_minute() >= self.target_minute
```

- [ ] **Step 3: Label**

In `_wait_label`, add a branch at the top:
```python
    def _wait_label(self) -> str:
        if self.wait_for_second_half:
            return "Second half starts soon..."
        if self.wait_for_lineups:
            return "Waiting for team sheets..."
        if self.target_minute is None:
            return "Playing to half time..."
        return f"Playing to minute {self.target_minute}'..."
```

- [ ] **Step 4: Run full suite + launch check**

Run: `.venv/Scripts/python -m pytest tests/ -q` (expect PASS) and
`.venv/Scripts/python src/main.py` (expect launch, then close).

- [ ] **Step 5: Commit**

```bash
git add src/ui/screens/live_wait_screen.py
git commit -m "feat(live_wait): wait_for_second_half mode (poll until 2H starts)"
```

---

## Task 7: Flow wiring -- half-aware LiveFlow + rewired start_live

**Files:**
- Modify: `src/ui/flow.py`

- [ ] **Step 1: Add config-derived label constants**

Near the other `_*` constants at the top of `flow.py` (after `_HALFTIME_LABEL`), add:
```python
_SECOND_HALF_LABEL = CONFIG["game"]["second_half_label"]
_FULLTIME_LABEL = CONFIG["game"]["fulltime_label"]
_JOIN_CUTOFF = CONFIG["live"]["join_cutoff_minute"]
_RESYNC_THRESHOLD = CONFIG["live"]["resync_threshold_seconds"]
```
Add the import for the new picker near the other game imports:
```python
from src.game.half_picker import pick_half
```
Add `RevealScreen` to the status-screens import (it shares the module with `FinalScreen`):
```python
from src.ui.screens.status_screens import FinalScreen, RevealScreen
```

- [ ] **Step 2: Make LiveFlow half-aware**

Replace the `LiveFlow.__init__` signature and body. Current:
```python
    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, pool: list[DraftedAthlete], plan: LivePlan,
                 sim: SimMode, on_snapshot=None) -> None:
        super().__init__(app, feed, pool, sim)
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self._scored = plan.scored_windows
        self.on_snapshot = on_snapshot
```
Replace with (drops the dead `plan`/`_scored`, adds half/clock/anchor + a back-to-picker
callback):
```python
    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, pool: list[DraftedAthlete], half: int,
                 clock: HalfClock, kickoff_epoch: float, sim: SimMode,
                 to_picker: "Callable[[], None]", on_snapshot=None) -> None:
        super().__init__(app, feed, pool, sim)
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self.half = half
        self.clock = clock                       # half-aware (start_minute set by caller)
        self.kickoff_epoch = kickoff_epoch
        self.to_picker = to_picker
        self.half_label = _SECOND_HALF_LABEL if half == 2 else _HALF_LABEL
        self.on_snapshot = on_snapshot
```
Add `Callable` to the typing import at the top of the file:
`from typing import TYPE_CHECKING, Callable, Optional`.

- [ ] **Step 3: Use the half label in the fixture banner**

In `LiveFlow._fixture`, change `"label": _HALF_LABEL,` to `"label": self.half_label,`.

- [ ] **Step 4: Build the screen from the caller's anchor**

Replace `LiveFlow._after_draft`. Current:
```python
    def _after_draft(self, selected: list[str]) -> None:
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        now_now = time.time()
        secs = seconds_to_kickoff(self.feed.kickoff_iso(), now_now)
        kickoff_epoch = now_now + secs if secs is not None else now_now
        match_clock = MatchClock(kickoff_epoch, self.clock)
        editing_start = match_clock.editing_window(now_now)
        available = self.session.roster.available()
        self.app.set_screen(LivePlayScreen(
            app=self.app, feed=self.feed, feed_client=self.feed_client,
            match_clock=match_clock, fixture_id=self.fixture_id,
            editing_window_start=editing_start, on_lock=self._on_lock,
            on_finished=self._to_final, poll_seconds=_POLL_SECONDS,
            available=available, sim=self.sim, on_snapshot=self.on_snapshot))
```
Replace with (uses the caller's fixed anchor; passes half label + threshold):
```python
    def _after_draft(self, selected: list[str]) -> None:
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        now_now = time.time()
        match_clock = MatchClock(self.kickoff_epoch, self.clock)
        editing_start = match_clock.editing_window(now_now)
        available = self.session.roster.available()
        self.app.set_screen(LivePlayScreen(
            app=self.app, feed=self.feed, feed_client=self.feed_client,
            match_clock=match_clock, fixture_id=self.fixture_id,
            editing_window_start=editing_start, on_lock=self._on_lock,
            on_finished=self._to_final, poll_seconds=_POLL_SECONDS,
            available=available, half_label=self.half_label,
            resync_threshold_seconds=_RESYNC_THRESHOLD,
            sim=self.sim, on_snapshot=self.on_snapshot))
```
(`seconds_to_kickoff` is no longer used in `_after_draft`; it stays imported for `start_live`.)

- [ ] **Step 5: Final screen titled by half, returns to picker**

Replace `LiveFlow._to_final`. Current:
```python
    def _to_final(self) -> None:
        team, opp = aggregate(self.score_codes)
        self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                        title=_HALFTIME_LABEL))
```
Replace with:
```python
    def _to_final(self) -> None:
        team, opp = aggregate(self.score_codes)
        title = _FULLTIME_LABEL if self.half == 2 else _HALFTIME_LABEL
        self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                        on_continue=self.to_picker, title=title))
```

- [ ] **Step 6: Rewire start_live for both halves**

Replace the `begin()` definition and the final `app.set_screen(...)` at the end of
`start_live`. Current:
```python
    def begin() -> None:
        clock = HalfClock(_HALF_MIN, _WINDOW_MIN)
        plan = live_plan(feed.current_minute(), feed.match_status(), clock)
        if not plan.scored_windows:
            app.set_screen(FinalScreen(app, 0, 0, "First half already over",
                                       title=_HALFTIME_LABEL))
            return
        pool = _pool_from_feed(feed)
        LiveFlow(app, feed, feed_client, fixture_id, pool, plan, sim,
                 on_snapshot=persist).start()

    app.set_screen(LiveWaitScreen(app, feed, feed_client, fixture_id,
                                  target_minute=None, on_ready=begin,
                                  poll_seconds=_POLL_SECONDS, sim=sim,
                                  wait_for_lineups=True))
```
Replace with:
```python
    def to_picker() -> None:
        start_live_select(app, sim_mode=sim_mode, is_lead=is_lead, username=username)

    def no_half_left() -> None:
        app.set_screen(RevealScreen(
            app, ["This match has no half left to play.", "Pick another match."],
            on_continue=to_picker))

    def launch_half(half: int) -> None:
        start_minute = 0 if half == 1 else _HALF_MIN
        clock = HalfClock(_HALF_MIN, _WINDOW_MIN, start_minute=start_minute)
        now_now = time.time()
        if half == 1:
            secs = seconds_to_kickoff(feed.kickoff_iso(), now_now)
            kickoff_epoch = now_now + secs if secs is not None else now_now
        else:
            in_half = max(0, feed.current_minute() - _HALF_MIN)
            kickoff_epoch = now_now - in_half * 60          # estimate; screen re-aligns
        elapsed_in_half = max(0, feed.current_minute() - start_minute)
        plan = live_plan(elapsed_in_half, feed.match_status(), clock)
        if not plan.scored_windows:
            no_half_left()
            return
        pool = _pool_from_feed(feed)
        LiveFlow(app, feed, feed_client, fixture_id, pool, half, clock,
                 kickoff_epoch, sim, to_picker, on_snapshot=persist).start()

    def begin() -> None:
        choice = pick_half(feed.status_short(), feed.current_minute(),
                           _HALF_MIN, _JOIN_CUTOFF)
        if choice.half is None:
            no_half_left()
        elif choice.needs_wait:
            app.set_screen(LiveWaitScreen(
                app, feed, feed_client, fixture_id, target_minute=None,
                on_ready=lambda: launch_half(2), poll_seconds=_POLL_SECONDS,
                sim=sim, wait_for_second_half=True))
        else:
            launch_half(choice.half)

    app.set_screen(LiveWaitScreen(app, feed, feed_client, fixture_id,
                                  target_minute=None, on_ready=begin,
                                  poll_seconds=_POLL_SECONDS, sim=sim,
                                  wait_for_lineups=True))
```

- [ ] **Step 7: Run full suite + launch**

Run: `.venv/Scripts/python -m pytest tests/ -q` (expect PASS).
Run: `.venv/Scripts/python src/main.py` (expect launch with no traceback, then close).

- [ ] **Step 8: Commit**

```bash
git add src/ui/flow.py
git commit -m "feat(flow): both-halves wiring -- pick_half, 2H wait, per-half final/picker"
```

---

## Task 8: live_schedule 2H contract test

**Files:**
- Modify: `tests/test_live_schedule.py`

- [ ] **Step 1: Add the 2H test**

Add to `tests/test_live_schedule.py` (it already imports `live_plan`, `LivePlan`,
`HalfClock`; match the existing import style in the file):
```python
def test_live_plan_second_half_with_half_relative_elapsed() -> None:
    # 2H clock; the caller passes HALF-RELATIVE elapsed (api_elapsed - 45) and mapped status.
    clock = HalfClock(45, 5, start_minute=45)
    # 8 minutes into the 2H (api minute 53): lobby = window 2, rest scored through ET.
    plan = live_plan(8, "live", clock)
    assert plan.lobby_window == 2
    assert plan.scored_windows == [3, 4, 5, 6, 7, 8, 9, clock.extra_time_window]

def test_live_plan_second_half_just_started_scores_full_half() -> None:
    clock = HalfClock(45, 5, start_minute=45)
    plan = live_plan(0, "live", clock)
    assert plan.scored_windows == list(range(1, 10)) + [clock.extra_time_window]
```

- [ ] **Step 2: Run + verify it passes (live_plan logic is offset-agnostic)**

Run: `.venv/Scripts/python -m pytest tests/test_live_schedule.py -q`
Expected: PASS (the function reads half-relative elapsed, so `start_minute` does not change
window-index math; this test locks the both-halves usage contract).

- [ ] **Step 3: Commit**

```bash
git add tests/test_live_schedule.py
git commit -m "test(live_schedule): lock 2H half-relative live_plan contract"
```

---

## Task 9: Headless 2H smoke

**Files:**
- Modify: `TOOLS/smoke_flow.py`

- [ ] **Step 1: Read the existing live_smoke for the pattern**

Open `TOOLS/smoke_flow.py` and find `live_smoke()` (the 1H headless driver). Reuse its
harness (fake app/screen, injected `now_fn`, a feed recording snapshots) for a 2H variant.

- [ ] **Step 2: Add live_smoke_2h()**

Add a `live_smoke_2h()` that:
- Builds `HalfClock(45, 5, start_minute=45)` and a `MatchClock` whose anchor is a
  deliberately-off 2H estimate (e.g. anchor set as if the half started, then drive the
  feed to report `2H` at api-minute 47+ so `realign` must snap).
- Constructs `LivePlayScreen(..., half_label="Second Half", resync_threshold_seconds=30,
  now_fn=<injected>)` with a stub `on_lock` returning a minimal `WindowReport` (reuse the
  existing live_smoke stub) and an `on_finished` that sets a flag.
- Advances injected time across 2H window boundaries, recording cumulative snapshots keyed
  by ABSOLUTE minute (45..90), withholding the `FT` status snapshot until after minute 90+.
- Asserts: 2H windows lock in order, `display_minute` reads in the 46-90 range during play,
  re-alignment changed the clock anchor at least once, and `on_finished` fired at `FT`.
- Prints `OK`/`FAIL` lines (ASCII only) and contributes to the script's non-zero exit on
  any failure (follow the existing `live_smoke` reporting convention).

- [ ] **Step 3: Wire it into the script's main run**

Call `live_smoke_2h()` alongside the existing smokes in the module's run section, so a
single `.venv/Scripts/python TOOLS/smoke_flow.py` exercises it.

- [ ] **Step 4: Run the smoke**

Run: `.venv/Scripts/python TOOLS/smoke_flow.py`
Expected: all sections print `OK`, process exits 0.

- [ ] **Step 5: Full suite + commit**

```bash
.venv/Scripts/python -m pytest tests/ -q
git add TOOLS/smoke_flow.py
git commit -m "test(smoke): headless second-half driver to full-time with re-align"
```

---

## Task 10: Build the deploy webzip

**Files:** none (build artifacts only)

- [ ] **Step 1: Mobile web build**

Run: `.venv/Scripts/python TOOLS/build_web_mobile.py --build-only`
Expected: prints `Design: 414 x 896`, ends with `Zip: .../WEB_BUILD/game_web_mobile.zip`.

- [ ] **Step 2: Deploy package**

Run: `.venv/Scripts/python TOOLS/package_deploy.py`
Expected: produces `PREDICTOR_deploy.zip` wrapping under `PREDICTOR/` (PHP + key included),
per the deploy-zip convention.

- [ ] **Step 3: Report artifact paths + sizes**

Print the final zip path(s) and size(s) so the user can upload via FTP/SFTP. Do NOT commit
build artifacts (WEB_BUILD/* is gitignored; confirm before adding anything).

- [ ] **Step 4: Log**

Append the build line to `log.md` and commit any source/log changes (not the zips).

---

## Self-Review

- **Spec coverage:** A (`half_picker` T4) / B anchor+realign (`MatchClock` T3, `start_live`
  T7, `LivePlayScreen` T5) / C half model (`HalfClock` T2, `display_minute` T3, T5) / D flow
  & screens (T5, T6, T7) / E config (T1) / F testing (T2-T5, T8, T9) + persistent half label
  (T5, T7) -- all mapped.
- **Type consistency:** `HalfChoice(half, needs_wait)`, `pick_half(status_short, elapsed,
  half_minutes, join_cutoff_minute)`, `MatchClock.realign(api_minute_in_half, now,
  threshold_seconds)`, `MatchClock.display_minute(now)`, `windows_to_enter(max_entered,
  playing_window)`, `LiveFlow(app, feed, feed_client, fixture_id, pool, half, clock,
  kickoff_epoch, sim, to_picker, on_snapshot)`, `LivePlayScreen(..., half_label,
  resync_threshold_seconds, ...)` -- names consistent across tasks.
- **No placeholders:** every code step shows complete code; T9 (smoke) describes the driver
  against the existing `live_smoke` harness it must mirror.
