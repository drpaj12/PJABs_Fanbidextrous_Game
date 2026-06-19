# Half-Game Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-device game into a faithful first half -- pre-game lobby, draft, 9 five-minute prediction windows (minutes 0-45), one Extra-Time window resolved over all stoppage, then a Half-Time summary.

**Architecture:** A new pure-logic `HalfClock` owns window boundaries and the half-over test. The feeds gain a `halftime` status and a `last_known_minute()` bound. The flow controller inserts a pre-game screen, loops 9 regular windows, runs one Extra-Time window whose end is discovered by polling the feed for a half-time status, then shows the existing FinalScreen worded "Half Time". The prediction engine (`session.py`, `prediction.py`, `window_report.py`) is untouched.

**Tech Stack:** Python 3.11, pygame-ce (UI only), pytest (pure-logic only). All numbers in `config/*.json`. Run tools via `.venv/Scripts/python`.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `config/game_config.json` | half length, labels, halftime status | modify |
| `config/layout_config.json` | pre-game screen geometry | modify |
| `src/game/half_clock.py` | window bounds, ET detection, half-over test (pure) | create |
| `tests/test_half_clock.py` | unit tests for HalfClock | create |
| `src/game/mock_feed.py` | add `last_known_minute()` | modify |
| `src/game/replay_feed.py` | synthesize a halftime status when absent | modify |
| `tests/test_feed_halftime.py` | feed halftime + delta tests | create |
| `src/ui/screens/play_screen.py` | optional `phase_label` in header | modify |
| `src/ui/screens/status_screens.py` | FinalScreen `title` param | modify |
| `src/ui/screens/pregame_screen.py` | fixture lobby + Start | create |
| `src/ui/flow.py` | pre-game insert, 9+ET windows, ET poll, half-time end | modify |
| `TOOLS/smoke_flow.py` | drive pre-game; assert 10 windows | modify |

---

## Task 1: Config keys for the half

**Files:**
- Modify: `config/game_config.json`
- Modify: `config/layout_config.json`

- [ ] **Step 1: Add half/labels/halftime keys to game_config.json**

In `config/game_config.json`, replace the `"game"` block (lines 22-27) with:

```json
  "game": {
    "roster_size": 6,
    "window_seconds": 300,
    "max_predictions_per_window": 5,
    "rng_seed": 99,
    "half_minutes": 45,
    "half_label": "First Half",
    "halftime_label": "Half Time",
    "extra_time_label": "Extra Time"
  },
```

And replace the `"feed"` block (lines 46-48) with:

```json
  "feed": {
    "poll_seconds": 120,
    "halftime_status": "halftime"
  },
```

- [ ] **Step 2: Add pre-game geometry to layout_config.json**

In `config/layout_config.json`, immediately after the `"room_code_size": 48,` line (line 30), insert:

```json

  "pregame_title_size": 30,
  "pregame_title_y": 140,
  "pregame_line_size": 22,
  "pregame_line_gap": 40,
  "pregame_lines_y": 300,
  "pregame_btn_w": 320,
  "pregame_btn_h": 64,
  "pregame_btn_y": 700,
```

- [ ] **Step 3: Verify both JSON files load**

Run (Bash tool):
```bash
.venv/Scripts/python -c "from src.utils.constants import CONFIG, LAYOUT; print(CONFIG['game']['half_minutes'], CONFIG['feed']['halftime_status'], LAYOUT.i('pregame_btn_y', 0))"
```
Expected: `45 halftime 700`

- [ ] **Step 4: Commit**

```bash
git add config/game_config.json config/layout_config.json
git commit -m "config: add half length, labels, halftime status, pre-game geometry"
```

---

## Task 2: HalfClock (pure logic)

**Files:**
- Create: `src/game/half_clock.py`
- Test: `tests/test_half_clock.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_half_clock.py`:

```python
# tests/test_half_clock.py
"""HalfClock is pure logic; no pygame here (golden rule)."""
from src.game.half_clock import HalfClock


def _clock() -> HalfClock:
    return HalfClock(half_minutes=45, window_minutes=5)


def test_regular_windows_tile_the_half():
    assert _clock().regular_windows == 9


def test_extra_time_window_follows_the_regular_windows():
    assert _clock().extra_time_window == 10


def test_first_window_covers_zero_to_five():
    c = _clock()
    assert (c.window_start(1), c.window_end(1)) == (0, 5)


def test_last_regular_window_covers_forty_to_forty_five():
    c = _clock()
    assert (c.window_start(9), c.window_end(9)) == (40, 45)


def test_regular_windows_are_not_extra_time():
    assert _clock().is_extra_time(9) is False


def test_the_tenth_window_is_extra_time():
    assert _clock().is_extra_time(10) is True


def test_extra_time_starts_at_the_half_mark():
    assert _clock().window_start(10) == 45


def test_half_over_only_on_the_halftime_status():
    assert HalfClock.is_half_over("halftime", "halftime") is True
    assert HalfClock.is_half_over("live", "halftime") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_half_clock.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.game.half_clock'`

- [ ] **Step 3: Write the implementation**

Create `src/game/half_clock.py`:

```python
# src/game/half_clock.py
"""Pure-logic clock for a single half: window boundaries, extra-time detection,
and the half-over test. No pygame, no I/O -- driven entirely by the config numbers
passed in, so it is fully unit-testable.

A half is `half_minutes` long, diced into fixed `window_minutes` windows. With a
45-minute half and 5-minute windows that is 9 regular windows (numbered 1..9,
covering minutes 0..45). One extra window -- index `regular_windows + 1` -- is the
Extra-Time window: it begins at the 45th minute and runs until the live feed
reports the half is over. Its end minute is therefore NOT computable here; the
caller discovers it by polling and asking is_half_over().
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class HalfClock:
    half_minutes: int
    window_minutes: int

    @property
    def regular_windows(self) -> int:
        """Number of fixed windows that tile the half (45 // 5 = 9)."""
        return self.half_minutes // self.window_minutes

    @property
    def extra_time_window(self) -> int:
        """1-based index of the single Extra-Time window (10 for a 9-window half)."""
        return self.regular_windows + 1

    def is_extra_time(self, window: int) -> bool:
        return window >= self.extra_time_window

    def window_start(self, window: int) -> int:
        """First minute of a window. Valid for regular and ET windows."""
        return (window - 1) * self.window_minutes

    def window_end(self, window: int) -> int:
        """Last minute of a REGULAR window. Meaningless for ET (end is discovered)."""
        return window * self.window_minutes

    @staticmethod
    def is_half_over(status: str, halftime_status: str) -> bool:
        return status == halftime_status
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_half_clock.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/game/half_clock.py tests/test_half_clock.py
git commit -m "feat: HalfClock window bounds + extra-time + half-over test"
```

---

## Task 3: Feed halftime support

**Files:**
- Modify: `src/game/mock_feed.py`
- Modify: `src/game/replay_feed.py`
- Test: `tests/test_feed_halftime.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_feed_halftime.py`:

```python
# tests/test_feed_halftime.py
"""Feeds expose a halftime status and a termination bound; pure data (no pygame)."""
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed


def _script() -> dict:
    return {
        "status_by_minute": [(0, "live"), (48, "halftime")],
        "snapshots": [
            {"minute": 45, "stats": {"corner_kicks": 9}},
            {"minute": 48, "stats": {"corner_kicks": 10}},
        ],
    }


def test_mock_feed_reports_halftime_status():
    f = MockFeed(_script())
    assert f.match_status_at(48) == "halftime"
    assert f.match_status_at(46) == "live"


def test_last_known_minute_is_the_largest_minute_seen():
    f = MockFeed(_script())
    assert f.last_known_minute() == 48


def test_last_known_minute_is_zero_when_empty():
    assert MockFeed({}).last_known_minute() == 0


def test_delta_across_stoppage():
    f = MockFeed(_script())
    a = f.snapshot_at(45)
    b = f.snapshot_at(48)
    assert b.delta(a, "corner_kicks") == 1


def test_replay_feed_synthesizes_halftime_at_default_half_mark_when_absent():
    script = {"status_by_minute": [(0, "live"), (96, "finished")],
              "snapshots": [{"minute": 45, "stats": {}}], "meta": {}}
    f = ReplayFeed(script)
    assert f.match_status_at(45) == "halftime"
    assert f.match_status_at(44) == "live"


def test_replay_feed_honours_meta_first_half_end():
    script = {"status_by_minute": [(0, "live"), (96, "finished")],
              "snapshots": [{"minute": 48, "stats": {}}],
              "meta": {"first_half_end_minute": 48}}
    f = ReplayFeed(script)
    assert f.match_status_at(47) == "live"
    assert f.match_status_at(48) == "halftime"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_feed_halftime.py -v`
Expected: FAIL with `AttributeError: 'MockFeed' object has no attribute 'last_known_minute'`

- [ ] **Step 3: Add `last_known_minute()` to MockFeed**

In `src/game/mock_feed.py`, add this method to the `MockFeed` class immediately after `match_status` (after line 33, before `lineups`):

```python
    def last_known_minute(self) -> int:
        """Largest minute the feed has data for -- the bound for an open poll loop."""
        minutes = list(self._snapshots) + [m for m, _ in self._status]
        return max(minutes) if minutes else 0
```

- [ ] **Step 4: Synthesize a halftime status in ReplayFeed**

Replace the entire body of `src/game/replay_feed.py` with:

```python
# src/game/replay_feed.py
"""Replay a recorded real match (a simulation file) through the EventFeed interface.

A simulation file is the same script schema MockFeed consumes (status_by_minute +
snapshots + lineups) plus a `meta` block describing the match. Generated offline from
StatsBomb open data by scripts/build_simulation_from_statsbomb.py; loaded here for
offline/deterministic play.

Recorded sims predate the half-game and carry no half-time status, so we synthesize
one: at `meta.first_half_end_minute` if present, else at the configured half mark.
The flow still discovers it by polling -- this only guarantees there is something to
discover.
"""
from src.game.mock_feed import MockFeed
from src.utils.constants import CONFIG, load_data

_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_HALF_MIN = CONFIG["game"]["half_minutes"]


class ReplayFeed(MockFeed):
    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.meta: dict = dict(script.get("meta", {}))
        if not any(s == _HALFTIME_STATUS for _, s in self._status):
            ht = int(self.meta.get("first_half_end_minute", _HALF_MIN))
            self._status = sorted(self._status + [(ht, _HALFTIME_STATUS)])

    @classmethod
    def from_file(cls, rel_path: str) -> "ReplayFeed":
        """Load a simulation file by repo-relative path (e.g. assets/data/simulations/x.json)."""
        return cls(load_data(rel_path))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_feed_halftime.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add src/game/mock_feed.py src/game/replay_feed.py tests/test_feed_halftime.py
git commit -m "feat: feed halftime status + last_known_minute bound"
```

---

## Task 4: PlayScreen phase label + FinalScreen title

**Files:**
- Modify: `src/ui/screens/play_screen.py:36-46`, `:211-214`
- Modify: `src/ui/screens/status_screens.py:61-80`

Note: these are pygame screens; the golden rule forbids pytest here. They are verified by the smoke flow in Task 7.

- [ ] **Step 1: Add `phase_label` to the PlayScreen constructor**

In `src/ui/screens/play_screen.py`, change the constructor signature and body. Replace lines 37-46:

```python
    def __init__(self, app: "App", available: list[DraftedAthlete],
                 on_submit: Callable[..., None], window: int,
                 sim: Optional[SimMode] = None,
                 last_report: Optional[WindowReport] = None) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.window = window
        self.sim = sim
        self.last_report = last_report
```

with:

```python
    def __init__(self, app: "App", available: list[DraftedAthlete],
                 on_submit: Callable[..., None], window: int,
                 sim: Optional[SimMode] = None,
                 last_report: Optional[WindowReport] = None,
                 phase_label: Optional[str] = None) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.window = window
        self.sim = sim
        self.last_report = last_report
        self.phase_label = phase_label
```

- [ ] **Step 2: Show the phase label in the header**

In `src/ui/screens/play_screen.py`, in `draw()`, replace lines 213-214:

```python
        hf = font(LAYOUT.i("play_window_size", 20))
        surface.blit(hf.render(f"Window {self.window}", True, _C["text_dim"]), (m, 16))
```

with:

```python
        hf = font(LAYOUT.i("play_window_size", 20))
        header = self.phase_label if self.phase_label else f"Window {self.window}"
        surface.blit(hf.render(header, True, _C["text_dim"]), (m, 16))
```

- [ ] **Step 3: Add a `title` param to FinalScreen**

In `src/ui/screens/status_screens.py`, replace the `FinalScreen.__init__` (lines 62-66):

```python
    def __init__(self, app: "App", team: int, opp: int, real_line: str | None,
                 on_continue: Optional[Callable[..., None]] = None) -> None:
        super().__init__(app)
        self.team, self.opp, self.real_line = team, opp, real_line
        self.on_continue = on_continue
```

with:

```python
    def __init__(self, app: "App", team: int, opp: int, real_line: str | None,
                 on_continue: Optional[Callable[..., None]] = None,
                 title: str = "Full Time") -> None:
        super().__init__(app)
        self.team, self.opp, self.real_line = team, opp, real_line
        self.on_continue = on_continue
        self.title = title
```

- [ ] **Step 4: Render the title**

In `src/ui/screens/status_screens.py`, in `FinalScreen.draw()`, replace line 79:

```python
        t = big.render("Full Time", True, _C["white"])
```

with:

```python
        t = big.render(self.title, True, _C["white"])
```

- [ ] **Step 5: Verify imports still resolve**

Run: `.venv/Scripts/python -c "import src.ui.screens.play_screen, src.ui.screens.status_screens; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/ui/screens/play_screen.py src/ui/screens/status_screens.py
git commit -m "feat: PlayScreen phase label + FinalScreen title param"
```

---

## Task 5: PregameScreen (fixture lobby)

**Files:**
- Create: `src/ui/screens/pregame_screen.py`

Note: pygame screen; verified by the smoke flow in Task 7.

- [ ] **Step 1: Create the pre-game screen**

Create `src/ui/screens/pregame_screen.py`:

```python
# src/ui/screens/pregame_screen.py
"""Pre-game lobby: shows the fixture and a Start button, then proceeds to the draft.

`fixture` is a dict with keys: home, away, competition, label. on_start() fires when
the player taps Start (or automatically once in SIM mode).
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]


class PregameScreen(Screen):
    def __init__(self, app: "App", fixture: dict, on_start: Callable[..., None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.fixture = fixture
        self.on_start = on_start
        self.sim = sim
        self._advanced = False
        sw = app.screen.get_width()
        bw = LAYOUT.i("pregame_btn_w", 320)
        bh = LAYOUT.i("pregame_btn_h", 64)
        x = (sw - bw) // 2
        self.start_btn = Button(
            pygame.Rect(x, LAYOUT.i("pregame_btn_y", 700), bw, bh), "Start First Half")

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and self.start_btn.hit(event.pos):
            self.on_start()

    def update(self, dt: float) -> None:
        if self.sim and self.sim.enabled and not self.sim.show_help and not self._advanced:
            self._advanced = True
            self.on_start()

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("pregame_title_size", 30))
        t = tf.render(self.fixture["competition"], True, _C["accent"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("pregame_title_y", 140))))
        lf = font(LAYOUT.i("pregame_line_size", 22))
        gap = LAYOUT.i("pregame_line_gap", 40)
        y = LAYOUT.i("pregame_lines_y", 300)
        rows = (self.fixture["home"], "vs", self.fixture["away"], self.fixture["label"])
        for i, text in enumerate(rows):
            col = _C["text_dim"] if i == 1 else _C["white"]
            line = lf.render(text, True, col)
            surface.blit(line, line.get_rect(center=(sw // 2, y + i * gap)))
        self.start_btn.draw(surface, lf)
```

- [ ] **Step 2: Verify it imports**

Run: `.venv/Scripts/python -c "import src.ui.screens.pregame_screen; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ui/screens/pregame_screen.py
git commit -m "feat: PregameScreen fixture lobby"
```

---

## Task 6: Flow controller -- pre-game, 9+ET windows, half-time end

**Files:**
- Modify: `src/ui/flow.py` (full rewrite)

Note: orchestration over pygame screens; verified by the smoke flow in Task 7.

- [ ] **Step 1: Rewrite flow.py**

Replace the entire contents of `src/ui/flow.py` with:

```python
# src/ui/flow.py
"""Full single-device flow controller.

Splash -> Room -> Pre-game -> Draft -> Play loop [Predict -> Cinematic] -> Half Time.
The half is `regular_windows` five-minute windows (minutes 0-45) plus one Extra-Time
window that resolves over all first-half stoppage, discovered by polling the feed for
a half-time status. The engine is untouched; meter before/after values are captured
around resolve_window to drive the cinematic.
"""
import random
from typing import TYPE_CHECKING, Optional
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed
from src.game.athlete import DraftedAthlete
from src.game.prediction import Prediction
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.game.cinematic import build_cinematic_script
from src.game.half_clock import HalfClock
from src.game.window_report import WindowReport, build_window_report
from src.ui.sim import SimMode
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
from src.ui.screens.pregame_screen import PregameScreen
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.ui.screens.cinematic_screen import CinematicScreen
from src.ui.screens.status_screens import FinalScreen
from src.utils.constants import CONFIG, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_STAT_LABELS = {s["code"]: s["label"] for s in _STATS_MENU["stats"]}
_THRESH = CONFIG["meter"]["success_threshold"]
_THRESH_C = CONFIG["meter"]["concede_threshold"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_HALF_MIN = CONFIG["game"]["half_minutes"]
_HALF_LABEL = CONFIG["game"]["half_label"]
_HALFTIME_LABEL = CONFIG["game"]["halftime_label"]
_ET_LABEL = CONFIG["game"]["extra_time_label"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_RNG_SEED = CONFIG["game"]["rng_seed"]


def _demo_pool() -> list[DraftedAthlete]:
    rows = [("sccr-1", "A. Davies", "Defender"), ("sccr-2", "J. David", "Attacker"),
            ("sccr-3", "S. Eustaquio", "Midfielder"), ("sccr-4", "M. Crepeau", "Goalkeeper"),
            ("sccr-5", "T. Buchanan", "Defender"), ("sccr-6", "C. Larin", "Attacker"),
            ("sccr-7", "I. Kone", "Midfielder"), ("sccr-8", "A. Hernandez", "Defender"),
            ("sccr-9", "L. Brym", "Attacker"), ("sccr-10", "M. Kone", "Midfielder")]
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="Canada", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _demo_script() -> dict:
    """A full first half: cumulative stats every 5 minutes 0-45, plus 3 minutes of
    stoppage (45 -> 48), with a halftime status at minute 48."""
    return {
        "status_by_minute": [(0, "live"), (48, "halftime")],
        "snapshots": [
            {"minute": 0,  "stats": {"corner_kicks": 0,  "shots_on_goal": 0, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 5,  "stats": {"corner_kicks": 1,  "shots_on_goal": 1, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 10, "stats": {"corner_kicks": 2,  "shots_on_goal": 2, "goalkeeper_saves": 1, "goals": 0, "cards": 0}},
            {"minute": 15, "stats": {"corner_kicks": 3,  "shots_on_goal": 3, "goalkeeper_saves": 1, "goals": 0, "cards": 1}},
            {"minute": 20, "stats": {"corner_kicks": 4,  "shots_on_goal": 4, "goalkeeper_saves": 2, "goals": 1, "cards": 1}},
            {"minute": 25, "stats": {"corner_kicks": 5,  "shots_on_goal": 5, "goalkeeper_saves": 2, "goals": 1, "cards": 1}},
            {"minute": 30, "stats": {"corner_kicks": 6,  "shots_on_goal": 6, "goalkeeper_saves": 3, "goals": 1, "cards": 1}},
            {"minute": 35, "stats": {"corner_kicks": 7,  "shots_on_goal": 7, "goalkeeper_saves": 3, "goals": 1, "cards": 2}},
            {"minute": 40, "stats": {"corner_kicks": 8,  "shots_on_goal": 8, "goalkeeper_saves": 4, "goals": 2, "cards": 2}},
            {"minute": 45, "stats": {"corner_kicks": 9,  "shots_on_goal": 9, "goalkeeper_saves": 4, "goals": 2, "cards": 2}},
            {"minute": 48, "stats": {"corner_kicks": 10, "shots_on_goal": 9, "goalkeeper_saves": 5, "goals": 2, "cards": 2}},
        ],
    }


def _pool_from_feed(feed: MockFeed) -> list[DraftedAthlete]:
    return [DraftedAthlete.create(athlete_id=r["athlete_id"], name=r["name"],
            broad_position=r["broad_position"], team=r["team"], jersey=int(r["jersey"]))
            for r in feed.lineups()]


class Flow:
    """Owns the screen sequence and shared state for one single-device half."""

    def __init__(self, app: "App", feed: MockFeed, pool: list[DraftedAthlete],
                 sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.sim = sim
        self.clock = HalfClock(_HALF_MIN, _WINDOW_MIN)
        self.last_report: Optional[WindowReport] = None
        self.session: Optional[GameSession] = None
        self.score_codes: list[str] = []
        self.window = 1
        self.app.global_handler = self.sim.handle_global
        self.app.overlay = self.sim.draw_overlay

    # -- flow steps --
    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._after_splash, self.sim))

    def _after_splash(self) -> None:
        self.app.set_screen(RoomScreen(self.app, self._after_room, self.sim))

    def _after_room(self, code: str) -> None:
        self.app.set_screen(PregameScreen(self.app, self._fixture(),
                                           self._after_pregame, self.sim))

    def _after_pregame(self) -> None:
        self.app.set_screen(DraftScreen(self.app, self.pool, self._after_draft,
                                        self.sim, title="Draft your six"))

    def _after_draft(self, selected: list[str]) -> None:
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        self._play_window()

    def _fixture(self) -> dict:
        meta = getattr(self.feed, "meta", {})
        return {
            "home": meta.get("home_team", "Canada"),
            "away": meta.get("away_team", "Opponent"),
            "competition": meta.get("competition", "Friendly"),
            "label": _HALF_LABEL,
        }

    def _play_window(self) -> None:
        available = self.session.roster.available()
        phase = _ET_LABEL if self.clock.is_extra_time(self.window) else None
        self.app.set_screen(PlayScreen(self.app, available, self._after_predict,
                                       self.window, self.sim, self.last_report,
                                       phase_label=phase))

    def _poll_half_end(self, start: int) -> int:
        """Emulate live polling: step forward from `start`, asking the feed its status
        each minute, and stop at the first minute the half is reported over (bounded by
        the feed's last known minute so a feed that never reports halftime terminates)."""
        last = self.feed.last_known_minute()
        m = start
        while m < last and not HalfClock.is_half_over(
                self.feed.match_status_at(m), _HALFTIME_STATUS):
            m += 1
        return m

    def _window_actuals(self) -> dict[str, int]:
        start = self.clock.window_start(self.window)
        if self.clock.is_extra_time(self.window):
            end = self._poll_half_end(start)
        else:
            end = self.clock.window_end(self.window)
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _after_predict(self, preds: list[Prediction], active_id: str,
                       use_power: bool) -> None:
        actuals = self._window_actuals()

        s_before = self.session.success_meter.value
        c_before = self.session.concede_meter.value
        res = self.session.resolve_window(window=self.window, predictions=preds,
                                           active_id=active_id, use_power=use_power,
                                           actuals=actuals)
        s_after = self.session.success_meter.value
        c_after = self.session.concede_meter.value
        for ev in res.score_events:
            self.score_codes.append(ev.to_code())

        self.last_report = build_window_report(
            window=self.window, predictions=preds, actuals=actuals,
            stat_labels=_STAT_LABELS, success_value=s_after, concede_value=c_after,
            success_threshold=_THRESH, concede_threshold=_THRESH_C,
            success_fired=res.success_fired, concede_fired=res.concede_fired,
            success_shot=res.success_shot, concede_shot=res.concede_shot)

        script = build_cinematic_script(
            predictions=preds, actuals=actuals,
            success_before=s_before, success_after=s_after, success_fired=res.success_fired,
            concede_before=c_before, concede_after=c_after, concede_fired=res.concede_fired,
            threshold=_THRESH, score_events=res.score_events, stat_labels=_STAT_LABELS)

        self.app.set_screen(CinematicScreen(self.app, script, self._after_cinematic, self.sim))

    def _after_cinematic(self) -> None:
        team, opp = aggregate(self.score_codes)
        if self.clock.is_extra_time(self.window):
            self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                            title=_HALFTIME_LABEL))
        else:
            self.window += 1
            self._play_window()


def start_simulation(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    Flow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()


def start(app: "App", sim_mode: bool = False) -> None:
    Flow(app, MockFeed(_demo_script()), _demo_pool(), SimMode(sim_mode)).start()
```

- [ ] **Step 2: Verify flow imports cleanly**

Run: `.venv/Scripts/python -c "from src.ui import flow; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ui/flow.py
git commit -m "feat: half-game flow -- pre-game, 9 windows + extra time, half-time end"
```

---

## Task 7: Smoke test the half end-to-end

**Files:**
- Modify: `TOOLS/smoke_flow.py:18-23`, `:34-48`, `:71-75`

- [ ] **Step 1: Import and drive the pre-game screen**

In `TOOLS/smoke_flow.py`, after the `from src.ui.screens.room import RoomScreen` line (line 20), add:

```python
from src.ui.screens.pregame_screen import PregameScreen
```

Then in `_drive`, after the `RoomScreen` branch (after line 43), add:

```python
    if isinstance(screen, PregameScreen):
        return []  # auto-advances on update in SIM
```

- [ ] **Step 2: Assert the half ran 10 windows**

In `TOOLS/smoke_flow.py`, replace the FinalScreen success branch (lines 71-75):

```python
        if isinstance(cur, FinalScreen):
            print("OK reached FinalScreen at frame", frame)
            print("OK screens seen:", sorted(seen))
            print("OK play windows entered:", windows_played)
            return 0
```

with:

```python
        if isinstance(cur, FinalScreen):
            ok = windows_played == 10  # 9 regular + 1 extra time
            print(("OK" if ok else "FAIL"), "reached FinalScreen at frame", frame)
            print("OK screens seen:", sorted(seen))
            print(("OK" if ok else "FAIL"), "play windows entered:", windows_played,
                  "(expected 10)")
            return 0 if ok else 1
```

- [ ] **Step 3: Run the demo smoke path**

Run (Bash tool):
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python TOOLS/smoke_flow.py
```
Expected: ends with `OK play windows entered: 10 (expected 10)` and exit status 0. Verify: `echo $?` prints `0`.

- [ ] **Step 4: Run a replay smoke path**

First list available sims:
```bash
ls assets/data/simulations/
```
Then run the smoke against the first slug shown (replace `<slug>` with a filename without `.json`):
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python TOOLS/smoke_flow.py <slug>
```
Expected: `OK play windows entered: 10 (expected 10)`, exit status 0.

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all tests pass (the prior 74 plus 8 HalfClock + 6 feed = 88), 0 failures.

- [ ] **Step 6: Confirm the desktop game still launches**

Run: `.venv/Scripts/python src/main.py`
Expected: a window opens, advances Splash -> Room -> Pre-game (shows fixture + "Start First Half"); tapping through reaches the draft and play windows. Close the window. (Manual visual check; no assertion.)

- [ ] **Step 7: Append to log.md and commit**

Append one line to `log.md`:
```
2026-06-19 | half-game flow: pre-game lobby + 9 windows + extra-time window (poll to half-time) + Half-Time summary | flow.py half_clock.py mock_feed.py replay_feed.py pregame_screen.py play_screen.py status_screens.py smoke_flow.py config
```

Then commit:
```bash
git add TOOLS/smoke_flow.py log.md
git commit -m "test: smoke the half-game to Half-Time (10 windows); log entry"
```

---

## Self-Review

**1. Spec coverage:**
- 9 regular windows minutes 0-45 -> HalfClock.regular_windows (Task 2) + flow loop (Task 6). ✓
- One Extra-Time window, all-5 screen labelled "Extra Time" -> phase_label (Task 4) + flow `_ET_LABEL` (Task 6). ✓
- ET resolves over all stoppage, end discovered by polling -> `_poll_half_end` + `is_half_over` (Tasks 2, 6). ✓
- Stoppage can extend / "extra extra time" -> poll loop bounded only by `last_known_minute` (Task 3, 6). ✓
- Pre-game lobby after the menu (Room -> Pre-game -> Draft) -> PregameScreen + flow insert (Tasks 5, 6). ✓
- Half-Time summary (FinalScreen worded "Half Time") -> FinalScreen `title` (Task 4) + flow (Task 6). ✓
- Live/sim parity (no pre-read of stoppage length) -> flow polls via feed status; no config stoppage length exists (Tasks 1, 6). ✓
- Recorded sims carry a half-time marker -> ReplayFeed synthesis (Task 3). ✓
- Edge: stoppage = 0 -> poll returns `start`, delta 0 (covered by ReplayFeed default at 45). ✓
- Tests: HalfClock ranges/ET/half-over (Task 2); feed halftime + delta (Task 3); smoke both paths reach Half-Time after 10 windows (Task 7). ✓
- Config keys half_minutes/half_label/extra_time_label/halftime_status (Task 1). ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; `<slug>` in Task 7 Step 4 is an intentional runtime value the engineer reads from `ls` output, not a code placeholder.

**3. Type consistency:** `HalfClock(half_minutes, window_minutes)` constructed identically in tests (Task 2) and flow (Task 6). `is_half_over(status, halftime_status)` static, called the same way in tests and `_poll_half_end`. `last_known_minute()` defined (Task 3) and called (Task 6). `phase_label` keyword defined (Task 4) and passed (Task 6). FinalScreen `title=` defined (Task 4) and passed (Task 6). `_fixture()` returns keys home/away/competition/label consumed by PregameScreen.draw (Task 5). Consistent.
