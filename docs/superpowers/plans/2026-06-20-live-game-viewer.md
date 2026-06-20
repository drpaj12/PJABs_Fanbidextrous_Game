# Live Game Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static config-driven live-match picker with a dynamic viewer that reads a curated local schedule, orders games soonest-first, shows each game's US Eastern kickoff and a live "how soon" status, and lets the player tap any not-yet-finished game.

**Architecture:** All time/status logic is pure Python in `src/game/schedule.py` (zero pygame, unit-tested). The picker screen `FixtureSelectScreen` becomes a scrollable list that reuses the existing `ScrollButtons` + clipped-viewport pattern; it computes the visible set each frame from an injected `now_fn` so relative labels update over time. `flow.start_live_select` loads `assets/data/schedule.json` and wires taps straight into the unchanged `start_live` flow. All tunables live in `config.live.schedule`.

**Tech Stack:** Python 3.11 (run via `.venv/Scripts/python`), pygame-ce (UI only), pytest. ASCII-only in all printed/logged output. No magic numbers (config), no globals, type hints on every signature, no pygame in `src/game/`.

---

## File Structure

- **Create** `src/game/schedule.py` — pure logic: `ScheduledGame` dataclass + `load_schedule`, `game_status`, `status_label`, `is_playable`, `visible_games`. Zero pygame.
- **Create** `assets/data/schedule.json` — curated World Cup + MLS games (`kickoff_utc` drives math, `kickoff_local` pre-baked Eastern string).
- **Create** `tests/test_schedule.py` — unit tests for `src/game/schedule.py` (no pygame).
- **Modify** `config/game_config.json` — add `live.schedule` block.
- **Modify** `config/layout_config.json` — add `fixsel_*` geometry keys.
- **Modify** `src/ui/screens/fixture_select_screen.py` — rebuild as a dynamic scrollable list.
- **Modify** `src/ui/flow.py` — `start_live_select` loads the schedule and constructs the new screen.
- **Modify** `TOOLS/smoke_flow.py` — add a headless schedule-screen check.

### Compatibility note (read before Task 5)

`start_live` still seeds the live feed's kickoff from `config.live.fixtures` (the three curated World Cup fixtures). Schedule games whose `id` is not in that list simply do not get a pre-seeded kickoff; the pre-game lobby then relies on the live API clock, which it already does. This is intentional and out of scope to change — `config.live.fixtures` and `config.live.fixture_id` both stay in config. Only the *picker source* changes (schedule.json), not the kickoff-seeding path.

### Commit trailer (every commit in this plan)

End every commit message body with this exact trailer line:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

All commits go to `main` (solo dev, no branches), then `git push`. Do NOT commit build artifacts (Task 8).

---

## Task 1: Config blocks (schedule tunables + layout geometry)

**Files:**
- Modify: `config/game_config.json:73-86` (the `live` block)
- Modify: `config/layout_config.json:131` (end of file, before closing brace)

- [ ] **Step 1: Add the `live.schedule` block**

In `config/game_config.json`, inside the `"live"` object, add a `"schedule"` key after `"fixtures"`. The `fixtures` array's closing `]` currently ends the `live` block; add a comma and the new key. Final `live` block:

```json
  "live": {
    "_comment": "fixture_id is the single-game default for --live; fixtures seeds the live feed kickoff for the curated set. The PICKER now reads assets/data/schedule.json (live.schedule) instead of fixtures. Free tier = 100 req/day; relay caches per fixture, fetches lineups once. warn_minutes_before: show a 'too early, come back later' notice when kickoff is further off than this. start_minutes_before: the lead does not poll the API until kickoff is within this many minutes (saves quota); a kickoff countdown shows meanwhile.",
    "fixture_id": 1539007,
    "competition_label": "FIFA World Cup 2026",
    "warn_minutes_before": 60,
    "start_minutes_before": 15,
    "join_cutoff_minute": 22,
    "resync_threshold_seconds": 30,
    "fixtures": [
      {"id": 1539007, "label": "Netherlands v Sweden", "kickoff": "2026-06-20T17:00:00+00:00"},
      {"id": 1489393, "label": "Germany v Ivory Coast", "kickoff": "2026-06-20T20:00:00+00:00"},
      {"id": 1539006, "label": "Turkiye v Paraguay", "kickoff": "2026-06-20T03:00:00+00:00"}
    ],
    "schedule": {
      "_comment": "Picker source. file = assets/data basename. lookahead_hours/drop_after_hours bound the rolling window; live_window_minutes is the generous span a game is treated as live (2 halves + stoppage + HT) since the viewer does not poll the API; soon_minutes is the 'soon' threshold.",
      "file": "schedule.json",
      "lookahead_hours": 48,
      "drop_after_hours": 4,
      "live_window_minutes": 150,
      "soon_minutes": 15
    }
  },
```

- [ ] **Step 2: Add the `fixsel_*` layout keys**

In `config/layout_config.json`, add these keys (place them after the `"popup_line_size": 18` entry; add a comma to that line first). They replace the in-code defaults the old picker used and add the new list geometry:

```json
  "popup_line_size": 18,

  "fixsel_title_size": 30,
  "fixsel_title_y": 150,
  "fixsel_list_top": 210,
  "fixsel_list_bottom_pad": 60,
  "fixsel_card_h": 76,
  "fixsel_card_gap": 10,
  "fixsel_card_title_size": 22,
  "fixsel_card_sub_size": 17,
  "fixsel_chip_size": 18,
  "fixsel_card_title_max": 26
```

- [ ] **Step 3: Verify both files parse as JSON**

Run: `.venv/Scripts/python -c "import json;json.load(open('config/game_config.json'));json.load(open('config/layout_config.json'));print('OK json valid')"`
Expected: `OK json valid`

- [ ] **Step 4: Commit**

```bash
git add config/game_config.json config/layout_config.json
git commit -m "feat(config): add live.schedule tunables and fixsel layout keys

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Curated schedule data file

**Files:**
- Create: `assets/data/schedule.json`

- [ ] **Step 1: Write the schedule file**

Create `assets/data/schedule.json`. `kickoff_utc` drives all math; `kickoff_local` is the pre-baked Eastern string (EDT = UTC-4 in June). Blank `home`/`away` exercise the round-descriptor fallback.

```json
{
  "_comment": "Curated live-game schedule for the viewer. kickoff_utc (ISO 8601 UTC) drives ALL time math; kickoff_local is a pre-baked US Eastern display string (EDT = UTC-4 in June 2026) -- no timezone code. home/away may be blank for undetermined knockout matchups; the round descriptor is shown instead. ids match API-Football fixture ids where known.",
  "games": [
    {"id": 1539006, "competition": "FIFA World Cup 2026", "home": "Turkiye", "away": "Paraguay", "round": "Group H", "kickoff_utc": "2026-06-20T03:00:00Z", "kickoff_local": "11:00 PM EDT (Jun 19)"},
    {"id": 1539007, "competition": "FIFA World Cup 2026", "home": "Netherlands", "away": "Sweden", "round": "Group F", "kickoff_utc": "2026-06-20T17:00:00Z", "kickoff_local": "1:00 PM EDT"},
    {"id": 1489393, "competition": "FIFA World Cup 2026", "home": "Germany", "away": "Ivory Coast", "round": "Group E", "kickoff_utc": "2026-06-20T20:00:00Z", "kickoff_local": "4:00 PM EDT"},
    {"id": 1539020, "competition": "FIFA World Cup 2026", "home": "Argentina", "away": "Mexico", "round": "Group D", "kickoff_utc": "2026-06-21T19:00:00Z", "kickoff_local": "3:00 PM EDT"},
    {"id": 9001, "competition": "MLS", "home": "Inter Miami", "away": "Orlando City", "round": "Matchday 20", "kickoff_utc": "2026-06-21T23:30:00Z", "kickoff_local": "7:30 PM EDT"},
    {"id": 9002, "competition": "MLS", "home": "LA Galaxy", "away": "Seattle Sounders", "round": "Matchday 20", "kickoff_utc": "2026-06-22T02:00:00Z", "kickoff_local": "10:00 PM EDT (Jun 21)"},
    {"id": 1539050, "competition": "FIFA World Cup 2026", "home": "", "away": "", "round": "Round of 16 - Match 50", "kickoff_utc": "2026-06-29T20:00:00Z", "kickoff_local": "4:00 PM EDT"}
  ]
}
```

- [ ] **Step 2: Verify it parses**

Run: `.venv/Scripts/python -c "import json;d=json.load(open('assets/data/schedule.json'));print('OK games', len(d['games']))"`
Expected: `OK games 7`

- [ ] **Step 3: Commit**

```bash
git add assets/data/schedule.json
git commit -m "feat(data): add curated World Cup + MLS schedule.json

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Pure schedule logic (TDD)

**Files:**
- Create: `src/game/schedule.py`
- Test: `tests/test_schedule.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schedule.py`. Tests are time-relative (derive `now` from each game's parsed kickoff) so no epoch is hand-computed.

```python
# tests/test_schedule.py
"""Pure schedule logic: title fallback, kickoff parsing, status/label heuristics, the
rolling-window filter. No pygame; deterministic via explicit `now` epochs."""
from datetime import datetime, timedelta, timezone

from src.game.schedule import (ScheduledGame, load_schedule, game_status,
                               status_label, is_playable, visible_games)

_BASE = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
NOW = _BASE.timestamp()
_CFG = {"lookahead_hours": 48, "drop_after_hours": 4,
        "live_window_minutes": 150, "soon_minutes": 15}


def _at(**delta) -> str:
    return (_BASE + timedelta(**delta)).isoformat()


def _game(kickoff: str = "2026-06-20T17:00:00Z", home: str = "A", away: str = "B",
          **kw) -> ScheduledGame:
    base = dict(id=1, competition="WC", home=home, away=away, round="Group A",
                kickoff_utc=kickoff, kickoff_local="1:00 PM EDT")
    base.update(kw)
    return ScheduledGame(**base)


def test_title_uses_teams_when_known() -> None:
    assert _game(home="Brazil", away="Spain").title() == "Brazil v Spain"


def test_title_falls_back_to_round_when_teams_blank() -> None:
    assert _game(home="", away="", round="Round of 16 - Match 50").title() == \
        "Round of 16 - Match 50"


def test_kickoff_epoch_parses_z_and_offset_equally() -> None:
    z = _game(kickoff="2026-06-20T17:00:00Z").kickoff_epoch()
    off = _game(kickoff="2026-06-20T17:00:00+00:00").kickoff_epoch()
    assert z is not None and z == off


def test_kickoff_epoch_none_for_bad_string() -> None:
    assert _game(kickoff="not-a-date").kickoff_epoch() is None


def test_game_status_boundaries() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert game_status(g, k - 1, 150) == "upcoming"
    assert game_status(g, k, 150) == "live"
    assert game_status(g, k + 150 * 60 - 1, 150) == "live"
    assert game_status(g, k + 150 * 60, 150) == "final"


def test_status_label_units_and_states() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert status_label(g, k - 15 * 60, soon_minutes=10, live_window_minutes=150) == "in 15m"
    assert status_label(g, k - 2 * 3600, 15, 150) == "in 2h"
    assert status_label(g, k - 24 * 3600, 15, 150) == "in 1d"
    assert status_label(g, k - 10 * 60, 15, 150) == "soon"
    assert status_label(g, k - 15 * 60, 15, 150) == "soon"   # boundary: secs == soon
    assert status_label(g, k, 15, 150) == "LIVE NOW"
    assert status_label(g, k + 200 * 60, 15, 150) == "Final"


def test_is_playable_true_for_upcoming_and_live_false_for_final() -> None:
    g = _game()
    k = g.kickoff_epoch()
    assert is_playable(g, k - 60, 150) is True       # upcoming
    assert is_playable(g, k + 60, 150) is True        # live
    assert is_playable(g, k + 200 * 60, 150) is False  # final


def test_visible_games_window_and_sort() -> None:
    games = [
        _game(kickoff=_at(hours=47), home="Soon", away="Edge"),    # within lookahead
        _game(kickoff=_at(hours=49), home="Far", away="X"),         # beyond lookahead
        _game(kickoff=_at(hours=-3), home="Recent", away="Y"),      # within drop_after
        _game(kickoff=_at(hours=-5), home="Old", away="Z"),         # beyond drop_after
        _game(kickoff="bad-date", home="Broken", away="Q"),         # unparseable -> dropped
    ]
    vis = visible_games(games, NOW, _CFG)
    assert [g.title() for g in vis] == ["Recent v Y", "Soon v Edge"]


def test_load_schedule_parses_good_and_skips_malformed() -> None:
    raw = {"games": [
        {"id": 1, "competition": "WC", "home": "A", "away": "B", "round": "Group A",
         "kickoff_utc": "2026-06-20T17:00:00Z", "kickoff_local": "1:00 PM EDT"},
        {"id": 2, "competition": "WC", "home": "C", "away": "D",
         "kickoff_utc": "2026-06-20T18:00:00Z", "kickoff_local": "2:00 PM EDT"},  # no round
        {"id": 3, "competition": "WC", "home": "E", "away": "F", "round": "Group B",
         "kickoff_utc": "nope", "kickoff_local": "x"},                            # bad time
    ]}
    games = load_schedule(raw)
    assert len(games) == 1
    assert games[0].id == 1


def test_load_schedule_empty_or_missing_games() -> None:
    assert load_schedule({}) == []
    assert load_schedule({"games": []}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_schedule.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.schedule'`

- [ ] **Step 3: Write the implementation**

Create `src/game/schedule.py`:

```python
# src/game/schedule.py
"""Pure schedule logic for the live-game viewer: parse a curated game list and derive each
game's status and 'how soon' label from the wall clock. ZERO pygame -- fully unit-tested.

Time math uses kickoff_utc (parsed to epoch) only. kickoff_local is a pre-baked US Eastern
display string the curator bakes EST/EDT correctness into, so no timezone library is needed
(the pygbag/WASM runtime ships no tzdata). Every time-dependent function takes `now` (epoch
seconds) as a parameter, so behavior is deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

_REQUIRED_KEYS = ("id", "competition", "home", "away", "round",
                  "kickoff_utc", "kickoff_local")
_DAY = 24 * 3600


def _parse_epoch(iso: Any) -> Optional[float]:
    """Parse an ISO 8601 UTC timestamp ('...Z' or '...+00:00') to epoch seconds, or None.

    Uses .timestamp() on a tz-aware datetime, so the result is independent of the host
    machine's local timezone (important for WASM and deterministic tests)."""
    if not isinstance(iso, str) or not iso:
        return None
    text = iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


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
        if self.home and self.away:
            return f"{self.home} v {self.away}"
        return self.round

    def kickoff_epoch(self) -> Optional[float]:
        """kickoff_utc parsed to epoch seconds, or None if unparseable."""
        return _parse_epoch(self.kickoff_utc)


def load_schedule(raw: dict) -> list[ScheduledGame]:
    """Parse raw['games'] into ScheduledGame objects, skipping any malformed record
    (not a dict, missing a required key, or with an unparseable kickoff_utc)."""
    games: list[ScheduledGame] = []
    for rec in (raw or {}).get("games", []):
        if not isinstance(rec, dict):
            continue
        if any(k not in rec for k in _REQUIRED_KEYS):
            continue
        if _parse_epoch(rec["kickoff_utc"]) is None:
            continue
        try:
            game = ScheduledGame(
                id=int(rec["id"]),
                competition=str(rec["competition"]),
                home=str(rec["home"]),
                away=str(rec["away"]),
                round=str(rec["round"]),
                kickoff_utc=str(rec["kickoff_utc"]),
                kickoff_local=str(rec["kickoff_local"]),
            )
        except (TypeError, ValueError):
            continue
        games.append(game)
    return games


def game_status(game: ScheduledGame, now: float, live_window_minutes: int) -> str:
    """'upcoming' before kickoff, 'live' during the generous live window, 'final' after.
    A game with no parseable kickoff is treated as 'final' (defensive)."""
    kickoff = game.kickoff_epoch()
    if kickoff is None:
        return "final"
    if now < kickoff:
        return "upcoming"
    if now < kickoff + live_window_minutes * 60:
        return "live"
    return "final"


def status_label(game: ScheduledGame, now: float, soon_minutes: int,
                 live_window_minutes: int) -> str:
    """Chip text: 'in 2h' / 'in 1d' / 'in 15m' / 'soon' / 'LIVE NOW' / 'Final'.
    For upcoming games the largest whole unit is used (days >= 24h, else hours >= 60m,
    else minutes); within soon_minutes of kickoff it reads 'soon'."""
    status = game_status(game, now, live_window_minutes)
    if status == "live":
        return "LIVE NOW"
    if status == "final":
        return "Final"
    kickoff = game.kickoff_epoch()
    secs = (kickoff if kickoff is not None else now) - now
    if secs <= soon_minutes * 60:
        return "soon"
    if secs >= _DAY:
        return f"in {int(secs // _DAY)}d"
    if secs >= 3600:
        return f"in {int(secs // 3600)}h"
    return f"in {int(secs // 60)}m"


def is_playable(game: ScheduledGame, now: float, live_window_minutes: int) -> bool:
    """Upcoming AND live games are tappable; finished games are not."""
    return game_status(game, now, live_window_minutes) != "final"


def visible_games(games: list[ScheduledGame], now: float,
                  cfg: dict) -> list[ScheduledGame]:
    """Rolling window: keep games from drop_after_hours after kickoff back through
    lookahead_hours before, sorted soonest-first. Records with no parseable kickoff drop."""
    lookahead = int(cfg["lookahead_hours"]) * 3600
    drop_after = int(cfg["drop_after_hours"]) * 3600
    kept: list[tuple[float, ScheduledGame]] = []
    for g in games:
        kickoff = g.kickoff_epoch()
        if kickoff is None:
            continue
        delta = kickoff - now
        if -drop_after <= delta <= lookahead:
            kept.append((kickoff, g))
    kept.sort(key=lambda pair: pair[0])
    return [g for _, g in kept]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_schedule.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (all prior tests + the new ones)

- [ ] **Step 6: Commit**

```bash
git add src/game/schedule.py tests/test_schedule.py
git commit -m "feat(game): pure schedule logic for the live-game viewer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Rebuild the picker as a dynamic scrollable list

**Files:**
- Modify (full rewrite): `src/ui/screens/fixture_select_screen.py`

This is a UI rewrite (pygame); it is exercised by the headless smoke in Task 6 (no pygame in unit tests). Steps 1-2 write the file; verification is the import check in Step 3 and the smoke in Task 6.

- [ ] **Step 1: Replace the file contents**

Overwrite `src/ui/screens/fixture_select_screen.py` with:

```python
# src/ui/screens/fixture_select_screen.py
"""Dynamic live-match picker: a scrollable list of curated games, soonest-first, each
showing its US Eastern kickoff and a 'how soon' status chip. Tapping a not-yet-finished
game enters the live flow via on_pick(game.id); finished games are greyed and untappable.

All time logic lives in src.game.schedule (pure). This file only renders + routes taps and
recomputes the visible set each frame from an injected now_fn, so relative labels stay live.
SIM auto-picks the first playable visible game so the headless/demo path keeps moving.
"""
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import ScrollButtons, font
from src.ui.sim import SimMode
from src.game.schedule import (ScheduledGame, visible_games, status_label,
                               game_status, is_playable)
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]


class FixtureSelectScreen(Screen):
    def __init__(self, app: "App", games: list[ScheduledGame],
                 on_pick: Callable[[int], None], cfg: dict,
                 sim: Optional[SimMode] = None,
                 now_fn: Callable[[], float] = time.time) -> None:
        super().__init__(app)
        self.games = games
        self.on_pick = on_pick
        self.cfg = cfg
        self.sim = sim
        self.now_fn = now_fn
        self._picked = False
        self.scroll = 0
        self._live_window = int(cfg["live_window_minutes"])
        self._soon = int(cfg["soon_minutes"])
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- which games show right now (rolling window, soonest-first) --
    def _visible(self) -> list[ScheduledGame]:
        return visible_games(self.games, self.now_fn(), self.cfg)

    # -- layout: the list scrolls inside a viewport below the title --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("fixsel_list_top", 210)
        bottom = self.app.screen.get_height() - LAYOUT.i("fixsel_list_bottom_pad", 60)
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _card_h(self) -> int:
        return LAYOUT.i("fixsel_card_h", 76)

    def _card_gap(self) -> int:
        return LAYOUT.i("fixsel_card_gap", 10)

    def _max_scroll(self, count: int) -> int:
        content_h = count * (self._card_h() + self._card_gap())
        return max(0, content_h - self._viewport().height)

    def _card_rect(self, i: int) -> pygame.Rect:
        vp = self._viewport()
        h = self._card_h()
        gap = self._card_gap()
        w = vp.width - ScrollButtons.gutter()
        return pygame.Rect(vp.x, vp.top + i * (h + gap) - self.scroll, w, h)

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self._picked:
            return
        visible = self._visible()
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(len(visible)),
                                     self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll,
                                                  self._max_scroll(len(visible)))
            return
        now = self.now_fn()
        for i, game in enumerate(visible):
            if not is_playable(game, now, self._live_window):
                continue
            if self._card_rect(i).collidepoint(event.pos):
                self._pick(game.id)
                return

    def _pick(self, fixture_id: int) -> None:
        if not self._picked:
            self._picked = True
            self.on_pick(fixture_id)

    def update(self, dt: float) -> None:
        if self._picked or not (self.sim and self.sim.enabled):
            return
        now = self.now_fn()
        for game in self._visible():
            if is_playable(game, now, self._live_window):
                self._pick(game.id)
                return

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render("Pick a live match", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))

        visible = self._visible()
        if not visible:
            self._draw_empty(surface)
            return

        now = self.now_fn()
        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        for i, game in enumerate(visible):
            r = self._card_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            self._draw_card(surface, r, game, now)
        surface.set_clip(prev)

        max_scroll = self._max_scroll(len(visible))
        if max_scroll > 0:
            self.scroll_btns.draw(surface, self.scroll, max_scroll)

    def _draw_empty(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        f = font(LAYOUT.i("ui_body_size", 22))
        msg = f.render("No games scheduled right now -- check back later", True,
                       _C["text_dim"])
        surface.blit(msg, msg.get_rect(center=(sw // 2, sh // 2)))

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect,
                   game: ScheduledGame, now: float) -> None:
        status = game_status(game, now, self._live_window)
        playable = status != "final"
        radius = LAYOUT.i("ui_corner_radius", 10)
        bg = _C["surface"] if playable else _C["background"]
        pygame.draw.rect(surface, bg, rect, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)

        title_col = _C["white"] if playable else _C["text_dim"]
        nmax = LAYOUT.i("fixsel_card_title_max", 26)
        nf = font(LAYOUT.i("fixsel_card_title_size", 22))
        surface.blit(nf.render(game.title()[:nmax], True, title_col),
                     (rect.x + 12, rect.y + 10))
        sf = font(LAYOUT.i("fixsel_card_sub_size", 17))
        surface.blit(sf.render(game.kickoff_local, True, _C["text_dim"]),
                     (rect.x + 12, rect.y + 42))

        chip = status_label(game, now, self._soon, self._live_window)
        chip_col = {"live": _C["accent"], "upcoming": _C["text"],
                    "final": _C["text_dim"]}[status]
        cf = font(LAYOUT.i("fixsel_chip_size", 18))
        chip_surf = cf.render(chip, True, chip_col)
        surface.blit(chip_surf,
                     chip_surf.get_rect(midright=(rect.right - 14, rect.centery)))
```

- [ ] **Step 2: Run the full test suite (imports still resolve)**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (unchanged count from Task 3; this file is not imported by `src/game` tests but Task 5 will import it).

- [ ] **Step 3: Verify the module imports cleanly under the dummy video driver**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "import src.ui.screens.fixture_select_screen as m; print('OK', m.FixtureSelectScreen.__name__)"`
Expected: `OK FixtureSelectScreen`

- [ ] **Step 4: Commit**

```bash
git add src/ui/screens/fixture_select_screen.py
git commit -m "feat(ui): rebuild fixture picker as dynamic scrollable schedule list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Wire the picker to the curated schedule

**Files:**
- Modify: `src/ui/flow.py:41` (import), `src/ui/flow.py:388-401` (`start_live_select`)

- [ ] **Step 1: Add the `load_schedule` import**

In `src/ui/flow.py`, the line:

```python
from src.ui.screens.fixture_select_screen import FixtureSelectScreen
```

Add immediately after it:

```python
from src.game.schedule import load_schedule
```

- [ ] **Step 2: Rewrite `start_live_select`**

Replace the whole `start_live_select` function (currently lines 388-401) with:

```python
def start_live_select(app: "App", sim_mode: bool = False,
                      is_lead: bool = False, username: str = "") -> None:
    """Show the dynamic live-match picker, then play the chosen game live. Reads the
    curated schedule (assets/data/schedule.json via live.schedule); the rolling-window
    viewer orders games soonest-first and lets the player tap any not-yet-finished game.
    Web/no-argument entry point for match day."""
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    sched_cfg = _LIVE["schedule"]
    try:
        raw = load_data(f'{CONFIG["assets"]["data_dir"]}/{sched_cfg["file"]}')
    except (OSError, ValueError):
        raw = {"games": []}                      # empty-state screen, never a crash
    games = load_schedule(raw)

    def picked(fixture_id: int) -> None:
        start_live(app, fixture_id, sim_mode=sim_mode, is_lead=is_lead,
                   username=username)

    app.set_screen(FixtureSelectScreen(app, games, picked, sched_cfg, sim))
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (`tests/test_live_flow_lock.py` imports `src.ui.flow`; this confirms the new import + function parse and the LiveFlow path is unbroken).

- [ ] **Step 4: Verify the game launches (desktop)**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "from src.ui import flow; print('OK flow import')"`
Expected: `OK flow import`

- [ ] **Step 5: Commit**

```bash
git add src/ui/flow.py
git commit -m "feat(ui): load curated schedule into the live picker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Headless schedule-screen smoke

**Files:**
- Modify: `TOOLS/smoke_flow.py` (add `schedule_smoke()` before `__main__`; extend `__main__`)

- [ ] **Step 1: Add the `schedule_smoke` function**

In `TOOLS/smoke_flow.py`, insert this function immediately before the `if __name__ == "__main__":` block (after `live_smoke_2h`):

```python
def schedule_smoke() -> int:
    """Drive the dynamic FixtureSelectScreen headlessly with a synthetic schedule + a fixed
    now_fn. Asserts the visible set is the rolling-window subset sorted soonest-first, that a
    finished game is not playable, and that SIM auto-picks the first PLAYABLE visible game's
    id. Returns 0 on OK."""
    from src.ui.app import App
    from src.game.schedule import ScheduledGame, visible_games
    from src.ui.screens.fixture_select_screen import FixtureSelectScreen
    from src.ui.sim import SimMode

    cfg = {"lookahead_hours": 48, "drop_after_hours": 4,
           "live_window_minutes": 150, "soon_minutes": 15}
    now = 1_000_000.0          # arbitrary fixed wall clock (epoch seconds)
    hour = 3600

    def g(gid: int, offset_h: float, home: str = "A", away: str = "B") -> ScheduledGame:
        # Build kickoff_utc by reusing the parser's inverse via a known epoch: store the
        # ISO of (now + offset). Use a fixed UTC reference so the string round-trips.
        from datetime import datetime, timezone, timedelta
        ref = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=now + offset_h * hour)
        return ScheduledGame(id=gid, competition="WC", home=home, away=away,
                             round="Group A", kickoff_utc=ref.isoformat(),
                             kickoff_local="TBD")

    games = [
        g(101, 2.0, "Soon", "One"),     # upcoming, in 2h  -> playable
        g(102, -1.0, "Live", "Now"),    # kicked off 1h ago -> live, playable
        g(103, -100.0, "Old", "Done"),  # long past         -> dropped by window
        g(104, 100.0, "Far", "Future"), # beyond lookahead  -> dropped by window
    ]

    # Expected visible set (sorted soonest-first): Live (-1h) then Soon (+2h).
    expect_titles = ["Live v Now", "Soon v One"]
    vis = visible_games(games, now, cfg)
    vis_ok = [x.title() for x in vis] == expect_titles

    app = App()
    picked: list[int] = []
    sim = SimMode(True)
    screen = FixtureSelectScreen(app, games, picked.append, cfg, sim, now_fn=lambda: now)
    screen.update(0.0)                  # SIM auto-pick on first update

    # First playable visible game is the live one (id 102).
    pick_ok = picked == [102]

    # Sanity: a draw pass must not raise (renders cards + chips for the visible set).
    draw_ok = True
    try:
        app.screen.fill((0, 0, 0))
        screen.draw(app.screen)
    except Exception as exc:            # pragma: no cover - smoke guard
        draw_ok = False
        print("FAIL schedule smoke: draw raised", exc)

    ok = vis_ok and pick_ok and draw_ok
    print(("OK" if vis_ok else "FAIL"),
          "schedule smoke: visible =", [x.title() for x in vis],
          "(expected", expect_titles, ")")
    print(("OK" if pick_ok else "FAIL"),
          "schedule smoke: SIM auto-picked =", picked, "(expected [102])")
    print(("OK" if draw_ok else "FAIL"), "schedule smoke: draw pass clean")
    return 0 if ok else 1
```

- [ ] **Step 2: Extend `__main__` to run it**

Replace the `if __name__ == "__main__":` block at the end of the file with:

```python
if __name__ == "__main__":
    rc_offline = main()
    rc_live = live_smoke()
    rc_live_2h = live_smoke_2h()
    rc_schedule = schedule_smoke()
    raise SystemExit(rc_offline or rc_live or rc_live_2h or rc_schedule)
```

- [ ] **Step 3: Run the smoke harness**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python TOOLS/smoke_flow.py`
Expected: all lines start with `OK`, including the three `schedule smoke:` lines; process exits 0.

- [ ] **Step 4: Run the full test suite once more**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add TOOLS/smoke_flow.py
git commit -m "test(smoke): headless check for the dynamic schedule picker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Changelog + push

**Files:**
- Modify: `log.md`

- [ ] **Step 1: Append a log line**

Append to `log.md` (ASCII only):

```
2026-06-20 | live game viewer: curated schedule.json + pure src/game/schedule.py + dynamic scrollable FixtureSelectScreen + flow wiring + schedule smoke | config/game_config.json, config/layout_config.json, assets/data/schedule.json, src/game/schedule.py, tests/test_schedule.py, src/ui/screens/fixture_select_screen.py, src/ui/flow.py, TOOLS/smoke_flow.py
```

- [ ] **Step 2: Commit and push**

```bash
git add log.md
git commit -m "docs(log): record live game viewer increment

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 8: Web build + deploy zip (NOT committed)

Build artifacts are gitignored and must NOT be committed. The mobile build does not auto-mirror into `WEB_BUILD/PREDICTOR/`; that mirror is a manual step before packaging.

- [ ] **Step 1: Build the mobile web bundle**

Run: `.venv/Scripts/python TOOLS/build_web_mobile.py --build-only`
Expected: build completes; output under `build/web/` (apk/tar.gz/index.html/favicon.png) and `WEB_BUILD/game_web_mobile.zip`. Note the fresh bundle name/stamp printed.

- [ ] **Step 2: Mirror the fresh client files into `WEB_BUILD/PREDICTOR/`**

Copy the fresh `*.apk`, `*.tar.gz`, `index.html`, and `favicon.png` from `build/web/` into `WEB_BUILD/PREDICTOR/`, removing any stale `*.apk`/`*.tar.gz` first. KEEP `WEB_BUILD/PREDICTOR/PHP_SCRIPTS/` (incl. `apifootball_key.txt`) and `DEPLOY_README.md` in place. Verify the bundle filename referenced inside the mirrored `index.html` matches the apk you copied.

- [ ] **Step 3: Package the deploy zip**

Run: `.venv/Scripts/python TOOLS/package_deploy.py`
Expected: `PREDICTOR_deploy.zip` produced (wraps everything under `PREDICTOR/`, includes PHP + key). Report its path and size.

- [ ] **Step 4: Report (do NOT commit)**

Print the deploy zip path + size and confirm working tree has no staged build artifacts (`git status` clean for tracked files).

---

## Self-Review

**1. Spec coverage:**
- Data model (`schedule.json`, all fields, blank teams, replaces `config.live.fixtures` as picker source) -> Task 2 + Task 5; `fixture_id` default kept -> Task 1 Step 1.
- Pure logic (`ScheduledGame.title/kickoff_epoch`, `load_schedule`, `game_status`, `status_label`, `is_playable`, `visible_games`) -> Task 3 (with tests).
- UI (dynamic scrollable list, `now_fn`, title/kickoff_local/status chip, greyed finals, empty state, ScrollButtons + wheel, SIM auto-pick first playable) -> Task 4.
- Wiring (`start_live_select` loads via `load_data` + `load_schedule`, passes `CONFIG["live"]["schedule"]` as cfg, `picked` -> `start_live` unchanged) -> Task 5.
- Config block (`live.schedule` with the five keys) -> Task 1.
- Errors/robustness (missing file, empty games, malformed rows, time-based Final) -> Task 1/2 (`_comment`), Task 3 (`load_schedule`/`game_status` defensive), Task 5 (try/except -> empty).
- Tests (`tests/test_schedule.py` covering title, kickoff parsing Z/offset/bad, status boundaries, label units + soon boundary + LIVE/Final, is_playable, visible window+sort+drop, load good/skip) -> Task 3.
- Smoke (synthetic games + fixed now_fn, visible/sorted/playable + SIM auto-pick) -> Task 6.

**2. Placeholder scan:** No TBD/TODO/"add error handling"/"similar to". Every code step has full code. (Smoke `kickoff_local: "TBD"` is literal display data in a synthetic test fixture, not a plan placeholder.)

**3. Type consistency:** `FixtureSelectScreen.__init__(app, games, on_pick, cfg, sim=None, now_fn=time.time)` is defined in Task 4 and called with exactly `(app, games, picked, sched_cfg, sim)` in Task 5 and `(app, games, picked.append, cfg, sim, now_fn=...)` in Task 6 (now_fn keyword). `visible_games(games, now, cfg)`, `game_status(game, now, live_window_minutes)`, `status_label(game, now, soon_minutes, live_window_minutes)`, `is_playable(game, now, live_window_minutes)` signatures match across Tasks 3/4/6. Config keys `live_window_minutes`/`soon_minutes`/`lookahead_hours`/`drop_after_hours`/`file` match between Task 1 and consumers. `ScheduledGame` field order matches all constructions.

All checks pass.
