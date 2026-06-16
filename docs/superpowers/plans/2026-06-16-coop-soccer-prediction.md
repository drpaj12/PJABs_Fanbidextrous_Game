# Coop Soccer Prediction Game Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cooperative, mobile-web-first soccer prediction game where two partners draft real athletes, make blind windowed over/under-as-integer predictions, fill local success/concede meters, fire shot attempts resolved by player conversion %, and accumulate a shared score against a shared opponent.

**Architecture:** A sport-agnostic pure-Python engine in `src/game/` (zero pygame, fully unit-tested) drives all rules. A soccer feed adapter normalizes API-Football JSON into generic `SportEvent`s behind an `EventFeed` protocol; a mock replay feed implements the same protocol for offline play and tests. A PHP relay on drpeterjamieson.com both syncs compact pick/score data via a flat file and caches the live feed server-side. A pygbag/WASM pygame UI in `src/ui/` renders a portrait mobile experience.

**Tech Stack:** Python 3.11, pygame-ce, pygbag, pytest, PHP (relay), API-Football (free tier). Venv at `.venv/Scripts/`.

---

## Reference: Authoritative Spec

This plan implements `docs/superpowers/specs/2026-06-16-coop-soccer-prediction-design.md`.
Read it before starting. Key locked decisions:

- Prediction = a single integer guess per stat. Code form `stat:N` (e.g. `corner:3`).
- Scoring bands (symmetric): exact -> +2 success; off-by-1 -> +1 success; off-by->1 -> +2 concede.
- Meters per-player, local. Crossing threshold fires a shot ATTEMPT resolved by conversion %.
- Goal-for -> shared team score; goal-against -> shared opponent score. Only result codes cross the wire.
- 6 athletes per hand, duplicates allowed, drafted simultaneously from both teams' lineups.
- 11 archetypes + 1-5 star rating, both seeded-hash-derived from athlete ID. 22 data-driven powers (this-window + next-window).
- Active-player rotation: pick from unused-this-cycle; reset when all 6 used.
- Mobile-web portrait is the build target. Relay payloads stay small (flat file).
- Data source API-Football (free); MUST be smoke-tested early (Phase 3 Task 3.1) before trusting it; mock feed is the fallback.

## Convention Notes (read once)

- **Python invocations:** ALWAYS `.venv/Scripts/python` and `.venv/Scripts/pytest` — never bare `python` (hits the MS Store stub).
- **ASCII only** in all `print()`, logs, and `.md` output. Use `OK`/`FAIL`, `->`, `===`. Unicode allowed only inside rendered pygame surfaces.
- **Type hints** on every function signature. **No globals.** **No magic numbers** — all constants from `config/game_config.json` via `src/utils/constants.py`, all power/rating data from `assets/data/`.
- `src/game/` imports NO pygame and NO soccer/API string literals in core logic.
- Tests live in `tests/`, test `src/game/` only, no pygame.
- Commit after every task with the shown message.

---

## File Structure

**Created/modified by this plan:**

- `config/game_config.json` — MODIFY: add all game constants (windows, scoring, meters, rotation, star formula, relay URL).
- `assets/data/powers.json` — CREATE: 11 archetypes, conversion baselines, 22 power effects.
- `assets/data/stats_menu.json` — CREATE: predictable-stat menu (finalized after smoke test).
- `src/utils/constants.py` — MODIFY: expose new config + a `load_data(filename)` helper.
- `src/game/sport_event.py` — CREATE: `SportEvent`, `WindowSnapshot`.
- `src/game/feed.py` — CREATE: `EventFeed` protocol.
- `src/game/athlete.py` — CREATE: `DraftedAthlete`, archetype/star derivation.
- `src/game/powers.py` — CREATE: `PowerEffect`, power loading + resolution.
- `src/game/roster.py` — CREATE: `Roster`, active-player rotation.
- `src/game/prediction.py` — CREATE: `Prediction` parse/serialize + grading bands.
- `src/game/meters.py` — CREATE: `Meter`, success/concede fill+fire+reset.
- `src/game/shot.py` — CREATE: conversion roll, attacker selection for concede.
- `src/game/session.py` — CREATE: `GameSession` — ties windows -> meters -> shot -> score_events.
- `src/game/scoring.py` — CREATE: shared-score aggregation from `score_event` codes.
- `src/game/mock_feed.py` — CREATE: replay `EventFeed` from a canned match.
- `src/game/normalize_soccer.py` — CREATE: API-Football JSON -> `SportEvent`/`WindowSnapshot` (pure).
- `src/sync/relay_client.py` — CREATE: async client matching the room/token/action relay (adapted from MULTIPLAYER/baseball_api.php).
- `src/sync/feed_client.py` — CREATE: GET cached feed snapshot from the relay (async).
- `src/sync/session_state.py` — CREATE: seed, window number, known picks, score_events.
- `scripts/smoke_test_apifootball.py` — CREATE: standalone free-key live verification.
- `scripts/capture_fixtures.py` — CREATE: save real API JSON to `tests/fixtures/`.
- `php/soccer_api.php` — CREATE: room/token/action relay adapted from the proven MULTIPLAYER/baseball_api.php; soccer phases + blind window reveal.
- `php/feed_cache.php` — CREATE: server-side fetch+cache of API-Football, served to clients.
- `php/.htaccess`, `php/game_rooms/.htaccess` — CREATE: CORS + deny direct JSON access (copied from MULTIPLAYER).
- `php/README.md` — CREATE: deploy + endpoint reference.
- `src/ui/screens/` — CREATE: pygame states (join, draft, predict, watch, reveal, final).
- `src/ui/widgets.py` — CREATE: mobile-friendly button, card, meter bar.
- `src/ui/app.py` — CREATE: async state machine + main loop.
- `src/main.py` / `main.py` — MODIFY: wire to `src/ui/app.py`.
- `tests/` — CREATE: one test module per `src/game/` module + adapter fixture tests.

---

## Phase 0: Scaffolding & Config

### Task 0.1: Initialize git and venv

**Files:** none created in-repo beyond `.venv/`.

- [ ] **Step 1: Initialize git and connect the existing GitHub remote (repo is not yet under version control locally)**

Run:
```bash
git init
git remote add origin https://github.com/drpaj12/PJABs_Fanbidextrous_Game.git
git add -A
git commit -m "chore: snapshot template + MULTIPLAYER reference before coop soccer build"
```
Expected: a root commit is created and `origin` points at the GitHub repo.
NOTE: Do NOT push in this plan — pushing is outbound and the GitHub repo may have divergent
history. Leave the push decision (and any rebase/merge with origin/main) to the user.

- [ ] **Step 2: Create the venv and install deps**

Run:
```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/pip install pygame-ce pygbag pytest
```
Expected: all three install without error.

- [ ] **Step 3: Verify pytest runs**

Run: `.venv/Scripts/pytest -q`
Expected: existing template tests collect and pass (or "no tests ran" — either is fine).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: pin pygame-ce, pygbag, pytest in venv"
```

---

### Task 0.2: Game config constants

**Files:**
- Modify: `config/game_config.json`

- [ ] **Step 1: Replace `config/game_config.json` with the full config**

```json
{
  "_comment": "All game constants live here. No magic numbers in code.",
  "display": {
    "title": "Coop Soccer Predictor",
    "width": 414,
    "height": 896,
    "fps": 60
  },
  "colors": {
    "background": [15, 16, 20],
    "surface":    [23, 25, 31],
    "border":     [44, 47, 58],
    "text":       [200, 204, 214],
    "text_dim":   [107, 112, 128],
    "accent":     [0, 245, 228],
    "white":      [238, 240, 245],
    "red":        [192, 57, 43],
    "green":      [39, 174, 96],
    "gold":       [184, 150, 10]
  },
  "game": {
    "roster_size": 6,
    "window_seconds": 300,
    "max_predictions_per_window": 2
  },
  "scoring": {
    "exact_credit": 2,
    "near_band": 1,
    "near_credit": 1,
    "miss_concede": 2
  },
  "meter": {
    "success_threshold": 6,
    "concede_threshold": 6
  },
  "rating": {
    "_comment": "magnitude = base * (mag_floor + mag_per_star * stars); conversion = conv_base + conv_per_star * stars",
    "mag_floor": 0.6,
    "mag_per_star": 0.2,
    "conv_per_star": 0.03,
    "min_stars": 1,
    "max_stars": 5
  },
  "feed": {
    "poll_seconds": 120
  },
  "relay": {
    "base_url": "https://drpeterjamieson.com/game",
    "sync_path": "/sync.php",
    "feed_path": "/feed_cache.php"
  },
  "assets": {
    "data_dir": "assets/data",
    "image_dir": "assets/images",
    "sound_dir": "assets/sounds",
    "powers_file": "assets/data/powers.json",
    "stats_menu_file": "assets/data/stats_menu.json"
  }
}
```

- [ ] **Step 2: Verify it is valid JSON**

Run: `.venv/Scripts/python -c "import json; json.load(open('config/game_config.json')); print('OK')"`
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add config/game_config.json
git commit -m "feat: full game config for coop soccer v1"
```

---

### Task 0.3: Powers data file

**Files:**
- Create: `assets/data/powers.json`

The 11 archetypes, each with a baseline conversion %, a this-window effect, and a
next-window effect. Effect `kind` values: `success_credit_add`, `success_credit_mult`,
`concede_credit_add`, `concede_credit_mult`, `conversion_add`, `negate_concede_shot`,
`none`. `value` is the base magnitude (scaled by star rating at resolution time).

- [ ] **Step 1: Create `assets/data/powers.json`**

```json
{
  "_comment": "22 power effects. magnitude scaled by star rating in code. Edit freely to rebalance.",
  "archetypes": {
    "GK":  { "group": "defense",   "conversion_base": 0.10,
             "this_window": { "kind": "negate_concede_shot", "value": 1.0 },
             "next_window": { "kind": "success_credit_add",  "value": -1.0 } },
    "CB":  { "group": "defense",   "conversion_base": 0.13,
             "this_window": { "kind": "concede_credit_mult", "value": 0.5 },
             "next_window": { "kind": "success_credit_add",  "value": -1.0 } },
    "FB":  { "group": "defense",   "conversion_base": 0.15,
             "this_window": { "kind": "concede_credit_add",  "value": -1.0 },
             "next_window": { "kind": "success_credit_add",  "value": -1.0 } },
    "WB":  { "group": "defense",   "conversion_base": 0.17,
             "this_window": { "kind": "concede_credit_add",  "value": -1.0 },
             "next_window": { "kind": "success_credit_add",  "value": -0.5 } },
    "DM":  { "group": "defense",   "conversion_base": 0.18,
             "this_window": { "kind": "concede_credit_mult", "value": 0.5 },
             "next_window": { "kind": "success_credit_add",  "value": -0.5 } },
    "CM":  { "group": "playmaker", "conversion_base": 0.20,
             "this_window": { "kind": "success_credit_add",  "value": 1.0 },
             "next_window": { "kind": "success_credit_add",  "value": 1.0 } },
    "AM":  { "group": "attack",    "conversion_base": 0.24,
             "this_window": { "kind": "success_credit_mult", "value": 2.0 },
             "next_window": { "kind": "concede_credit_add",  "value": 1.0 } },
    "WG":  { "group": "attack",    "conversion_base": 0.26,
             "this_window": { "kind": "conversion_add",      "value": 0.15 },
             "next_window": { "kind": "concede_credit_add",  "value": 1.0 } },
    "SS":  { "group": "attack",    "conversion_base": 0.30,
             "this_window": { "kind": "success_credit_add",  "value": 2.0 },
             "next_window": { "kind": "concede_credit_add",  "value": 1.0 } },
    "ST":  { "group": "attack",    "conversion_base": 0.35,
             "this_window": { "kind": "conversion_add",      "value": 0.20 },
             "next_window": { "kind": "concede_credit_add",  "value": 1.5 } }
  },
  "broad_position_map": {
    "Goalkeeper": ["GK"],
    "Defender":   ["CB", "FB", "WB"],
    "Midfielder": ["DM", "CM", "AM"],
    "Attacker":   ["WG", "SS", "ST"]
  }
}
```

Note: 10 archetypes are listed (GK, CB, FB, WB, DM, CM, AM, WG, SS, ST). The spec's 11th
distinction (Winger L/R) is treated as one `WG` archetype per the spec ("Winger (L/R treated
the same)"), giving 10 distinct archetypes x 2 effects = 20 base effects plus per-star
scaling variation. If a true 11th is desired later, add it here only — no code change.

- [ ] **Step 2: Validate JSON**

Run: `.venv/Scripts/python -c "import json; d=json.load(open('assets/data/powers.json')); print(len(d['archetypes']), 'archetypes OK')"`
Expected: prints `10 archetypes OK`.

- [ ] **Step 3: Commit**

```bash
git add assets/data/powers.json
git commit -m "feat: data-driven power table for 10 soccer archetypes"
```

---

### Task 0.4: Stats menu data file (provisional, finalized after smoke test)

**Files:**
- Create: `assets/data/stats_menu.json`

- [ ] **Step 1: Create `assets/data/stats_menu.json`**

```json
{
  "_comment": "Predictable stats. kind=incident (count occurrences) or delta (end-minus-start). Finalize 'api_field' after the Phase 3 smoke test confirms real field names.",
  "stats": [
    { "code": "goal",   "label": "Goals",          "kind": "incident", "api_field": "goals",         "default_line": 1 },
    { "code": "corner", "label": "Corners",        "kind": "delta",    "api_field": "corner_kicks",  "default_line": 3 },
    { "code": "shot",   "label": "Shots on target","kind": "delta",    "api_field": "shots_on_goal", "default_line": 2 },
    { "code": "card",   "label": "Cards",          "kind": "incident", "api_field": "cards",         "default_line": 1 },
    { "code": "save",   "label": "Saves",          "kind": "delta",    "api_field": "goalkeeper_saves","default_line": 2 }
  ]
}
```

- [ ] **Step 2: Validate JSON**

Run: `.venv/Scripts/python -c "import json; json.load(open('assets/data/stats_menu.json')); print('OK')"`
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add assets/data/stats_menu.json
git commit -m "feat: provisional predictable-stat menu (api fields pending smoke test)"
```

---

### Task 0.5: Constants loader + data helper

**Files:**
- Modify: `src/utils/constants.py`
- Test: `tests/test_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constants.py
from src.utils.constants import CONFIG, load_data


def test_config_has_game_section():
    assert CONFIG["game"]["roster_size"] == 6
    assert CONFIG["game"]["window_seconds"] == 300


def test_load_data_reads_powers():
    powers = load_data(CONFIG["assets"]["powers_file"])
    assert "archetypes" in powers
    assert powers["archetypes"]["ST"]["conversion_base"] == 0.35
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_constants.py -v`
Expected: FAIL (ImportError on `load_data` or missing keys).

- [ ] **Step 3: Read current constants.py, then implement**

Read `src/utils/constants.py` first to preserve its CONFIG-loading approach, then ensure it exposes:

```python
# src/utils/constants.py  (add load_data; keep existing CONFIG load)
import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]


def _load_json(rel_path: str) -> dict[str, Any]:
    with open(_ROOT / rel_path, encoding="utf-8") as fh:
        return json.load(fh)


CONFIG: dict[str, Any] = _load_json("config/game_config.json")


def load_data(rel_path: str) -> dict[str, Any]:
    """Load a JSON data file by repo-relative path (e.g. assets/data/powers.json)."""
    return _load_json(rel_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_constants.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/utils/constants.py tests/test_constants.py
git commit -m "feat: constants loader exposes CONFIG and load_data helper"
```

---

## Phase 1: Generic Engine Core (`src/game/`, pure Python, TDD)

### Task 1.1: SportEvent and WindowSnapshot models

**Files:**
- Create: `src/game/sport_event.py`
- Test: `tests/test_sport_event.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sport_event.py
from src.game.sport_event import SportEvent, WindowSnapshot


def test_sport_event_holds_athletes_and_type():
    ev = SportEvent(event_id="sccr-1", event_type="goal",
                    athlete_ids=["sccr-501"], team="CAN",
                    minute=34, detail="Normal Goal")
    assert ev.event_type == "goal"
    assert "sccr-501" in ev.athlete_ids


def test_window_snapshot_delta():
    start = WindowSnapshot(minute=0, stats={"corner_kicks": 2, "goals": 0})
    end = WindowSnapshot(minute=5, stats={"corner_kicks": 5, "goals": 1})
    assert end.delta(start, "corner_kicks") == 3
    assert end.delta(start, "goals") == 1
    assert end.delta(start, "missing_field") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_sport_event.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/sport_event.py
"""Sport-agnostic event and per-window stat snapshot. Zero pygame, zero soccer literals."""
from dataclasses import dataclass, field


@dataclass
class SportEvent:
    event_id: str
    event_type: str
    athlete_ids: list[str] = field(default_factory=list)
    team: str = ""
    minute: int = 0
    detail: str = ""


@dataclass
class WindowSnapshot:
    """Cumulative match stats observed at a given minute."""
    minute: int
    stats: dict[str, int] = field(default_factory=dict)

    def delta(self, earlier: "WindowSnapshot", field_name: str) -> int:
        return self.stats.get(field_name, 0) - earlier.stats.get(field_name, 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_sport_event.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/sport_event.py tests/test_sport_event.py
git commit -m "feat: SportEvent and WindowSnapshot models"
```

---

### Task 1.2: EventFeed protocol

**Files:**
- Create: `src/game/feed.py`
- Test: `tests/test_feed_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feed_protocol.py
from src.game.feed import EventFeed
from src.game.sport_event import WindowSnapshot, SportEvent


class _Stub:
    def snapshot_at(self, minute: int) -> WindowSnapshot:
        return WindowSnapshot(minute=minute, stats={"goals": 0})

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    def match_status(self) -> str:
        return "live"


def test_stub_satisfies_protocol():
    feed: EventFeed = _Stub()
    assert feed.snapshot_at(5).minute == 5
    assert feed.events_between(0, 5) == []
    assert feed.match_status() == "live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_feed_protocol.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/feed.py
"""EventFeed protocol: the only feed interface the engine depends on."""
from typing import Protocol
from src.game.sport_event import SportEvent, WindowSnapshot


class EventFeed(Protocol):
    def snapshot_at(self, minute: int) -> WindowSnapshot: ...
    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]: ...
    def match_status(self) -> str: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_feed_protocol.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/game/feed.py tests/test_feed_protocol.py
git commit -m "feat: EventFeed protocol"
```

---

### Task 1.3: Athlete archetype + star derivation (seeded, deterministic)

**Files:**
- Create: `src/game/athlete.py`
- Test: `tests/test_athlete.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_athlete.py
from src.game.athlete import DraftedAthlete, derive_archetype, derive_stars


def test_archetype_is_deterministic_and_in_bucket():
    a1 = derive_archetype("sccr-501", "Defender")
    a2 = derive_archetype("sccr-501", "Defender")
    assert a1 == a2
    assert a1 in ("CB", "FB", "WB")


def test_stars_deterministic_in_range():
    s1 = derive_stars("sccr-501")
    s2 = derive_stars("sccr-501")
    assert s1 == s2
    assert 1 <= s1 <= 5


def test_drafted_athlete_carries_derived_fields():
    ath = DraftedAthlete.create(athlete_id="sccr-7", name="A. Davies",
                                broad_position="Defender", team="CAN", jersey=19)
    assert ath.archetype in ("CB", "FB", "WB")
    assert 1 <= ath.stars <= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_athlete.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/athlete.py
"""Drafted athlete + deterministic archetype/star derivation from athlete id."""
import hashlib
from dataclasses import dataclass
from src.utils.constants import CONFIG, load_data

_POWERS = load_data(CONFIG["assets"]["powers_file"])
_BUCKET_MAP: dict[str, list[str]] = _POWERS["broad_position_map"]
_MIN_STARS: int = CONFIG["rating"]["min_stars"]
_MAX_STARS: int = CONFIG["rating"]["max_stars"]


def _hash_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def derive_archetype(athlete_id: str, broad_position: str) -> str:
    options = _BUCKET_MAP.get(broad_position, _BUCKET_MAP["Midfielder"])
    return options[_hash_int("arch:" + athlete_id) % len(options)]


def derive_stars(athlete_id: str) -> int:
    span = _MAX_STARS - _MIN_STARS + 1
    return _MIN_STARS + (_hash_int("star:" + athlete_id) % span)


@dataclass
class DraftedAthlete:
    athlete_id: str
    name: str
    broad_position: str
    team: str
    jersey: int
    archetype: str
    stars: int

    @classmethod
    def create(cls, athlete_id: str, name: str, broad_position: str,
               team: str, jersey: int) -> "DraftedAthlete":
        return cls(
            athlete_id=athlete_id, name=name, broad_position=broad_position,
            team=team, jersey=jersey,
            archetype=derive_archetype(athlete_id, broad_position),
            stars=derive_stars(athlete_id),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_athlete.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/athlete.py tests/test_athlete.py
git commit -m "feat: deterministic archetype and star derivation"
```

---

### Task 1.4: Power loading, star scaling, and conversion %

**Files:**
- Create: `src/game/powers.py`
- Test: `tests/test_powers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_powers.py
from src.game.athlete import DraftedAthlete
from src.game.powers import (
    scaled_magnitude, conversion_for, this_window_effect, next_window_effect,
)


def _striker() -> DraftedAthlete:
    # find an id that hashes to ST is brittle; build directly:
    return DraftedAthlete(athlete_id="x", name="S", broad_position="Attacker",
                          team="T", jersey=9, archetype="ST", stars=5)


def test_scaled_magnitude_uses_star_formula():
    # base 1.0, 5 stars -> 0.6 + 0.2*5 = 1.6
    assert abs(scaled_magnitude(1.0, 5) - 1.6) < 1e-9
    # 1 star -> 0.6 + 0.2 = 0.8
    assert abs(scaled_magnitude(1.0, 1) - 0.8) < 1e-9


def test_conversion_includes_star_bonus():
    ath = _striker()
    # ST base 0.35 + conv_per_star(0.03)*5 = 0.50
    assert abs(conversion_for(ath) - 0.50) < 1e-9


def test_effects_return_kind_and_scaled_value():
    ath = _striker()
    tw = this_window_effect(ath)
    assert tw["kind"] == "conversion_add"
    # base 0.20 scaled by 5-star magnitude 1.6 -> 0.32
    assert abs(tw["value"] - 0.32) < 1e-9
    nw = next_window_effect(ath)
    assert nw["kind"] == "concede_credit_add"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_powers.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/powers.py
"""Power resolution: load the data table, scale effects by star rating."""
from src.utils.constants import CONFIG, load_data
from src.game.athlete import DraftedAthlete

_POWERS = load_data(CONFIG["assets"]["powers_file"])
_ARCH = _POWERS["archetypes"]
_R = CONFIG["rating"]


def scaled_magnitude(base: float, stars: int) -> float:
    return base * (_R["mag_floor"] + _R["mag_per_star"] * stars)


def conversion_for(athlete: DraftedAthlete) -> float:
    base = _ARCH[athlete.archetype]["conversion_base"]
    return base + _R["conv_per_star"] * athlete.stars


def _effect(athlete: DraftedAthlete, slot: str) -> dict:
    raw = _ARCH[athlete.archetype][slot]
    return {"kind": raw["kind"], "value": scaled_magnitude(raw["value"], athlete.stars)}


def this_window_effect(athlete: DraftedAthlete) -> dict:
    return _effect(athlete, "this_window")


def next_window_effect(athlete: DraftedAthlete) -> dict:
    return _effect(athlete, "next_window")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_powers.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/powers.py tests/test_powers.py
git commit -m "feat: star-scaled power effects and conversion percentages"
```

---

### Task 1.5: Roster + active-player rotation

**Files:**
- Create: `src/game/roster.py`
- Test: `tests/test_roster.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roster.py
import pytest
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster


def _hand(n: int) -> list[DraftedAthlete]:
    return [DraftedAthlete(athlete_id=f"a{i}", name=f"P{i}",
            broad_position="Midfielder", team="T", jersey=i,
            archetype="CM", stars=3) for i in range(n)]


def test_available_excludes_used_until_cycle_resets():
    r = Roster(_hand(6))
    assert len(r.available()) == 6
    r.use("a0")
    assert "a0" not in [a.athlete_id for a in r.available()]
    for i in range(1, 6):
        r.use(f"a{i}")
    # all 6 used -> cycle resets, all available again
    assert len(r.available()) == 6


def test_use_unavailable_raises():
    r = Roster(_hand(6))
    r.use("a0")
    with pytest.raises(ValueError):
        r.use("a0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_roster.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/roster.py
"""A player's 6-athlete hand and the active-player rotation."""
from src.game.athlete import DraftedAthlete


class Roster:
    def __init__(self, athletes: list[DraftedAthlete]) -> None:
        self._athletes: list[DraftedAthlete] = list(athletes)
        self._used_ids: set[str] = set()

    def all_athletes(self) -> list[DraftedAthlete]:
        return list(self._athletes)

    def get(self, athlete_id: str) -> DraftedAthlete:
        for a in self._athletes:
            if a.athlete_id == athlete_id:
                return a
        raise KeyError(athlete_id)

    def available(self) -> list[DraftedAthlete]:
        return [a for a in self._athletes if a.athlete_id not in self._used_ids]

    def use(self, athlete_id: str) -> None:
        if athlete_id in self._used_ids:
            raise ValueError(f"athlete {athlete_id} already used this cycle")
        if athlete_id not in {a.athlete_id for a in self._athletes}:
            raise ValueError(f"athlete {athlete_id} not in roster")
        self._used_ids.add(athlete_id)
        if len(self._used_ids) >= len(self._athletes):
            self._used_ids.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_roster.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/roster.py tests/test_roster.py
git commit -m "feat: roster with cycle-resetting active-player rotation"
```

---

### Task 1.6: Prediction parsing + serialization

**Files:**
- Create: `src/game/prediction.py`
- Test: `tests/test_prediction_parse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prediction_parse.py
import pytest
from src.game.prediction import Prediction


def test_round_trip_code():
    p = Prediction(stat_code="corner", line=3)
    assert p.to_code() == "corner:3"
    assert Prediction.from_code("corner:3") == p


def test_from_code_rejects_garbage():
    with pytest.raises(ValueError):
        Prediction.from_code("nonsense")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_prediction_parse.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/prediction.py
"""A single integer prediction for one stat in one window. Code form: stat:N."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Prediction:
    stat_code: str
    line: int

    def to_code(self) -> str:
        return f"{self.stat_code}:{self.line}"

    @classmethod
    def from_code(cls, code: str) -> "Prediction":
        if ":" not in code:
            raise ValueError(f"bad prediction code: {code!r}")
        stat, _, num = code.partition(":")
        if not stat or not num.lstrip("-").isdigit():
            raise ValueError(f"bad prediction code: {code!r}")
        return cls(stat_code=stat, line=int(num))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_prediction_parse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/game/prediction.py tests/test_prediction_parse.py
git commit -m "feat: Prediction parse/serialize (stat:N codes)"
```

---

### Task 1.7: Band grading (prediction vs actual -> credit)

**Files:**
- Modify: `src/game/prediction.py`
- Test: `tests/test_prediction_grade.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prediction_grade.py
from src.game.prediction import Prediction, grade


def test_exact_gives_success_credit_2():
    g = grade(Prediction("corner", 3), actual=3)
    assert g.success_credit == 2 and g.concede_credit == 0


def test_off_by_one_gives_success_credit_1():
    g = grade(Prediction("corner", 3), actual=4)
    assert g.success_credit == 1 and g.concede_credit == 0
    g2 = grade(Prediction("corner", 3), actual=2)
    assert g2.success_credit == 1 and g2.concede_credit == 0


def test_off_by_more_than_one_gives_concede_2():
    g = grade(Prediction("corner", 3), actual=6)
    assert g.success_credit == 0 and g.concede_credit == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_prediction_grade.py -v`
Expected: FAIL (`grade` undefined).

- [ ] **Step 3: Implement (append to prediction.py)**

```python
# append to src/game/prediction.py
from src.utils.constants import CONFIG

_S = CONFIG["scoring"]


@dataclass(frozen=True)
class Grade:
    success_credit: int
    concede_credit: int


def grade(prediction: "Prediction", actual: int) -> Grade:
    diff = abs(prediction.line - actual)
    if diff == 0:
        return Grade(success_credit=_S["exact_credit"], concede_credit=0)
    if diff <= _S["near_band"]:
        return Grade(success_credit=_S["near_credit"], concede_credit=0)
    return Grade(success_credit=0, concede_credit=_S["miss_concede"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_prediction_grade.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/prediction.py tests/test_prediction_grade.py
git commit -m "feat: threshold-band grading"
```

---

### Task 1.8: Meter fill / fire / reset

**Files:**
- Create: `src/game/meters.py`
- Test: `tests/test_meters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_meters.py
from src.game.meters import Meter


def test_add_below_threshold_does_not_fire():
    m = Meter(threshold=6)
    assert m.add(4) is False
    assert m.value == 4


def test_add_reaching_threshold_fires_and_resets():
    m = Meter(threshold=6)
    assert m.add(6) is True
    assert m.value == 0


def test_negative_credit_floors_at_zero():
    m = Meter(threshold=6)
    m.add(1)
    m.add(-5)
    assert m.value == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_meters.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/meters.py
"""A fillable meter that fires (and resets) when it reaches its threshold."""


class Meter:
    def __init__(self, threshold: int) -> None:
        self.threshold: int = threshold
        self.value: int = 0

    def add(self, credit: int) -> bool:
        """Add credit. Return True if the meter fired (and was reset)."""
        self.value = max(0, self.value + credit)
        if self.value >= self.threshold:
            self.value = 0
            return True
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_meters.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/meters.py tests/test_meters.py
git commit -m "feat: Meter fill/fire/reset"
```

---

### Task 1.9: Shot resolution (conversion roll + concede attacker pick)

**Files:**
- Create: `src/game/shot.py`
- Test: `tests/test_shot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shot.py
import random
from src.game.athlete import DraftedAthlete
from src.game.shot import resolve_shot, pick_concede_attacker


def _ath(aid: str, arch: str, stars: int) -> DraftedAthlete:
    return DraftedAthlete(athlete_id=aid, name=aid, broad_position="Attacker",
                          team="T", jersey=1, archetype=arch, stars=stars)


def test_resolve_shot_is_deterministic_with_seeded_rng():
    rng = random.Random(42)
    ath = _ath("s", "ST", 5)  # conversion 0.50
    results = [resolve_shot(ath, rng, bonus=0.0) for _ in range(4)]
    rng2 = random.Random(42)
    results2 = [resolve_shot(ath, rng2, bonus=0.0) for _ in range(4)]
    assert results == results2


def test_bonus_can_force_certain_goal():
    rng = random.Random(1)
    ath = _ath("s", "GK", 1)  # low conversion
    assert resolve_shot(ath, rng, bonus=1.0) is True


def test_pick_concede_attacker_excludes_owned():
    pool = [_ath("p1", "ST", 3), _ath("p2", "WG", 3), _ath("p3", "CM", 3)]
    owned = {"p1", "p2"}
    rng = random.Random(0)
    chosen = pick_concede_attacker(pool, owned, rng)
    assert chosen.athlete_id == "p3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_shot.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/shot.py
"""Shot-attempt resolution. Local randomness; results are transmitted, not the rolls."""
import random
from src.game.athlete import DraftedAthlete
from src.game.powers import conversion_for


def resolve_shot(attacker: DraftedAthlete, rng: random.Random, bonus: float = 0.0) -> bool:
    """True if the shot scores. bonus is an additive conversion modifier (e.g. from a power)."""
    chance = conversion_for(attacker) + bonus
    return rng.random() < chance


def pick_concede_attacker(pool: list[DraftedAthlete], owned_ids: set[str],
                          rng: random.Random) -> DraftedAthlete:
    """Pick a threatening attacker from the pool, excluding the player's own athletes."""
    candidates = [a for a in pool if a.athlete_id not in owned_ids]
    if not candidates:
        candidates = list(pool)
    return candidates[rng.randrange(len(candidates))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_shot.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/shot.py tests/test_shot.py
git commit -m "feat: shot resolution and concede-attacker selection"
```

---

### Task 1.10: Score-event codes + shared aggregation

**Files:**
- Create: `src/game/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scoring.py
from src.game.scoring import ScoreEvent, aggregate


def test_score_event_round_trip():
    ev = ScoreEvent(slot=0, window=3, side="for", scored=True)
    assert ScoreEvent.from_code(ev.to_code()) == ev


def test_aggregate_counts_only_scored_goals():
    codes = [
        ScoreEvent(0, 1, "for", True).to_code(),
        ScoreEvent(1, 1, "for", False).to_code(),   # missed, no goal
        ScoreEvent(1, 2, "for", True).to_code(),
        ScoreEvent(0, 2, "against", True).to_code(),
    ]
    team, opp = aggregate(codes)
    assert team == 2
    assert opp == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_scoring.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/scoring.py
"""Compact score-event codes that cross the relay, and shared-score aggregation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreEvent:
    slot: int       # 0 = player A, 1 = player B
    window: int
    side: str       # "for" or "against"
    scored: bool

    def to_code(self) -> str:
        return f"{self.slot}:{self.window}:{self.side}:{1 if self.scored else 0}"

    @classmethod
    def from_code(cls, code: str) -> "ScoreEvent":
        slot, window, side, scored = code.split(":")
        return cls(slot=int(slot), window=int(window), side=side, scored=scored == "1")


def aggregate(codes: list[str]) -> tuple[int, int]:
    """Return (shared_team_score, shared_opponent_score)."""
    team = opp = 0
    for code in codes:
        ev = ScoreEvent.from_code(code)
        if not ev.scored:
            continue
        if ev.side == "for":
            team += 1
        elif ev.side == "against":
            opp += 1
    return team, opp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_scoring.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/game/scoring.py tests/test_scoring.py
git commit -m "feat: score-event codes and shared-score aggregation"
```

---

### Task 1.11: GameSession — resolve a window end-to-end

**Files:**
- Create: `src/game/session.py`
- Test: `tests/test_session.py`

This ties the pieces together: given a player's locked predictions, chosen active player,
power-on flag, and the actual window stats, apply this-window power effects, grade each
prediction into success/concede credit, add to meters, fire shot attempts, apply pending
next-window effects, and emit `ScoreEvent`s.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
import random
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.prediction import Prediction
from src.game.session import GameSession, WindowResolution


def _hand() -> list[DraftedAthlete]:
    specs = [("a0", "ST", 5), ("a1", "CB", 3), ("a2", "CM", 4),
             ("a3", "GK", 2), ("a4", "WG", 3), ("a5", "DM", 3)]
    return [DraftedAthlete(athlete_id=i, name=i, broad_position="Midfielder",
            team="T", jersey=0, archetype=arch, stars=st) for i, arch, st in specs]


def test_exact_predictions_fill_success_meter_and_can_fire():
    pool = _hand()
    session = GameSession(slot=0, roster=Roster(_hand()), pool=pool,
                          rng=random.Random(7))
    # Three exact predictions = 3 * 2 = 6 success credit = threshold -> fires once.
    preds = [Prediction("corner", 3), Prediction("shot", 2)]
    actuals = {"corner": 3, "shot": 2, "goal": 0, "card": 0, "save": 0}
    res: WindowResolution = session.resolve_window(
        window=1, predictions=preds, active_id="a0", use_power=False, actuals=actuals)
    # 2 exact preds -> 4 success credit, below threshold 6, no fire yet.
    assert session.success_meter.value == 4
    assert res.score_events == []


def test_big_miss_fills_concede_meter():
    session = GameSession(slot=0, roster=Roster(_hand()), pool=_hand(),
                          rng=random.Random(7))
    preds = [Prediction("corner", 0), Prediction("shot", 0)]
    actuals = {"corner": 9, "shot": 9, "goal": 0, "card": 0, "save": 0}
    session.resolve_window(window=1, predictions=preds, active_id="a1",
                           use_power=False, actuals=actuals)
    # 2 big misses -> 2 * 2 = 4 concede credit.
    assert session.concede_meter.value == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_session.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/session.py
"""Per-player session state: resolves one window's predictions into meter/score changes."""
import random
from dataclasses import dataclass, field
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.prediction import Prediction, grade
from src.game.meters import Meter
from src.game.powers import this_window_effect, next_window_effect
from src.game.shot import resolve_shot, pick_concede_attacker
from src.game.scoring import ScoreEvent
from src.utils.constants import CONFIG


@dataclass
class WindowResolution:
    success_fired: bool
    concede_fired: bool
    score_events: list[ScoreEvent] = field(default_factory=list)


class GameSession:
    def __init__(self, slot: int, roster: Roster, pool: list[DraftedAthlete],
                 rng: random.Random) -> None:
        self.slot = slot
        self.roster = roster
        self.pool = pool
        self.rng = rng
        self.success_meter = Meter(CONFIG["meter"]["success_threshold"])
        self.concede_meter = Meter(CONFIG["meter"]["concede_threshold"])
        self._owned_ids = {a.athlete_id for a in roster.all_athletes()}
        self._pending_next: dict = {"kind": "none", "value": 0.0}

    def _apply_credit_effects(self, effect: dict, success: int, concede: int) -> tuple[int, int]:
        kind, val = effect["kind"], effect["value"]
        if kind == "success_credit_add":
            success += round(val)
        elif kind == "success_credit_mult":
            success = round(success * val)
        elif kind == "concede_credit_add":
            concede += round(val)
        elif kind == "concede_credit_mult":
            concede = round(concede * val)
        return success, concede

    def resolve_window(self, window: int, predictions: list[Prediction],
                       active_id: str, use_power: bool, actuals: dict[str, int]) -> WindowResolution:
        active = self.roster.get(active_id)
        self.roster.use(active_id)

        success = concede = 0
        for p in predictions:
            g = grade(p, actuals.get(p.stat_code, 0))
            success += g.success_credit
            concede += g.concede_credit

        # Pending next-window effect from the previous window's power.
        success, concede = self._apply_credit_effects(self._pending_next, success, concede)
        self._pending_next = {"kind": "none", "value": 0.0}

        conversion_bonus = 0.0
        negate_concede = False
        if use_power:
            tw = this_window_effect(active)
            if tw["kind"] == "conversion_add":
                conversion_bonus = tw["value"]
            elif tw["kind"] == "negate_concede_shot":
                negate_concede = True
            else:
                success, concede = self._apply_credit_effects(tw, success, concede)
            self._pending_next = next_window_effect(active)

        success = max(0, success)
        concede = max(0, concede)

        events: list[ScoreEvent] = []
        success_fired = self.success_meter.add(success)
        if success_fired:
            scored = resolve_shot(active, self.rng, bonus=conversion_bonus)
            events.append(ScoreEvent(self.slot, window, "for", scored))

        concede_fired = self.concede_meter.add(concede)
        if concede_fired:
            if negate_concede:
                events.append(ScoreEvent(self.slot, window, "against", False))
            else:
                attacker = pick_concede_attacker(self.pool, self._owned_ids, self.rng)
                scored = resolve_shot(attacker, self.rng)
                events.append(ScoreEvent(self.slot, window, "against", scored))

        return WindowResolution(success_fired, concede_fired, events)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_session.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full engine suite**

Run: `.venv/Scripts/pytest tests/ -v`
Expected: all Phase 0-1 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/game/session.py tests/test_session.py
git commit -m "feat: GameSession resolves a window into meters and score events"
```

---

## Phase 2: Feeds (mock + soccer adapter)

### Task 2.1: Mock replay feed

**Files:**
- Create: `src/game/mock_feed.py`
- Test: `tests/test_mock_feed.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mock_feed.py
from src.game.mock_feed import MockFeed
from src.game.feed import EventFeed


def test_mock_feed_snapshots_and_status():
    script = {
        "status_by_minute": [(0, "live"), (90, "finished")],
        "snapshots": [
            {"minute": 0, "stats": {"corner_kicks": 0, "goals": 0}},
            {"minute": 5, "stats": {"corner_kicks": 3, "goals": 1}},
        ],
        "lineups": [],
    }
    feed: EventFeed = MockFeed(script)
    assert feed.snapshot_at(5).stats["corner_kicks"] == 3
    assert feed.snapshot_at(0).stats["goals"] == 0
    assert feed.match_status_at(0) == "live"
    assert feed.match_status_at(90) == "finished"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_mock_feed.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/game/mock_feed.py
"""A canned replay feed implementing EventFeed, for offline play and tests."""
from src.game.sport_event import SportEvent, WindowSnapshot


class MockFeed:
    def __init__(self, script: dict) -> None:
        self._snapshots = {s["minute"]: WindowSnapshot(minute=s["minute"], stats=dict(s["stats"]))
                           for s in script.get("snapshots", [])}
        self._status = sorted(script.get("status_by_minute", [(0, "live")]))
        self._lineups = script.get("lineups", [])

    def snapshot_at(self, minute: int) -> WindowSnapshot:
        if minute in self._snapshots:
            return self._snapshots[minute]
        # nearest earlier snapshot, else empty
        earlier = [m for m in self._snapshots if m <= minute]
        if earlier:
            return self._snapshots[max(earlier)]
        return WindowSnapshot(minute=minute, stats={})

    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]:
        return []

    def match_status_at(self, minute: int) -> str:
        status = "live"
        for m, s in self._status:
            if m <= minute:
                status = s
        return status

    def match_status(self) -> str:
        return self._status[-1][1] if self._status else "live"

    def lineups(self) -> list[dict]:
        return list(self._lineups)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_mock_feed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/game/mock_feed.py tests/test_mock_feed.py
git commit -m "feat: mock replay feed for offline play and tests"
```

---

### Task 2.2: Soccer normalize adapter (API-Football JSON -> models)

**Files:**
- Create: `src/game/normalize_soccer.py`
- Create: `tests/fixtures/apifootball_lineups_sample.json` (hand-authored minimal sample)
- Create: `tests/fixtures/apifootball_statistics_sample.json`
- Test: `tests/test_normalize_soccer.py`

NOTE: Real field names are confirmed/adjusted in Phase 3 after the smoke test. This task
uses the documented API-Football v3 shapes; if the smoke test reveals differences, update
this adapter and its fixtures in Phase 3 Task 3.2.

- [ ] **Step 1: Create the fixture files**

`tests/fixtures/apifootball_lineups_sample.json`:
```json
{
  "response": [
    {
      "team": {"id": 26, "name": "Canada"},
      "startXI": [
        {"player": {"id": 501, "name": "A. Davies", "number": 19, "pos": "D"}},
        {"player": {"id": 502, "name": "J. David", "number": 20, "pos": "F"}}
      ],
      "substitutes": [
        {"player": {"id": 503, "name": "S. Larin", "number": 17, "pos": "F"}}
      ]
    }
  ]
}
```

`tests/fixtures/apifootball_statistics_sample.json`:
```json
{
  "response": [
    {
      "team": {"id": 26, "name": "Canada"},
      "statistics": [
        {"type": "Corner Kicks", "value": 5},
        {"type": "Shots on Goal", "value": 4},
        {"type": "Goalkeeper Saves", "value": 2}
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_normalize_soccer.py
import json
from pathlib import Path
from src.game.normalize_soccer import parse_lineups, parse_statistics
from src.game.athlete import DraftedAthlete

FIX = Path(__file__).parent / "fixtures"


def test_parse_lineups_returns_drafted_athletes():
    data = json.loads((FIX / "apifootball_lineups_sample.json").read_text())
    athletes = parse_lineups(data)
    ids = {a.athlete_id for a in athletes}
    assert "sccr-501" in ids
    davies = next(a for a in athletes if a.athlete_id == "sccr-501")
    assert isinstance(davies, DraftedAthlete)
    assert davies.broad_position == "Defender"
    assert davies.team == "Canada"


def test_parse_statistics_to_stat_dict():
    data = json.loads((FIX / "apifootball_statistics_sample.json").read_text())
    stats = parse_statistics(data)
    assert stats["corner_kicks"] == 5
    assert stats["shots_on_goal"] == 4
    assert stats["goalkeeper_saves"] == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_normalize_soccer.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement**

```python
# src/game/normalize_soccer.py
"""Pure normalization of API-Football v3 JSON into engine models. No network here."""
from src.game.athlete import DraftedAthlete

_POS_MAP = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}
_STAT_FIELD = {
    "Corner Kicks": "corner_kicks",
    "Shots on Goal": "shots_on_goal",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total Shots": "total_shots",
    "Fouls": "fouls",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
}


def _athlete(player: dict, team_name: str) -> DraftedAthlete:
    p = player["player"]
    broad = _POS_MAP.get((p.get("pos") or "M").upper()[:1], "Midfielder")
    return DraftedAthlete.create(
        athlete_id=f"sccr-{p['id']}", name=p.get("name", "Unknown"),
        broad_position=broad, team=team_name, jersey=p.get("number") or 0)


def parse_lineups(data: dict) -> list[DraftedAthlete]:
    out: list[DraftedAthlete] = []
    for team_block in data.get("response", []):
        team_name = team_block.get("team", {}).get("name", "")
        for group in ("startXI", "substitutes"):
            for player in team_block.get(group, []) or []:
                out.append(_athlete(player, team_name))
    return out


def parse_statistics(data: dict) -> dict[str, int]:
    stats: dict[str, int] = {}
    for team_block in data.get("response", []):
        for entry in team_block.get("statistics", []) or []:
            field_name = _STAT_FIELD.get(entry.get("type", ""))
            if field_name is None:
                continue
            value = entry.get("value")
            stats[field_name] = stats.get(field_name, 0) + int(value or 0)
    return stats
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_normalize_soccer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/game/normalize_soccer.py tests/test_normalize_soccer.py tests/fixtures/apifootball_lineups_sample.json tests/fixtures/apifootball_statistics_sample.json
git commit -m "feat: soccer normalize adapter (API-Football v3 shapes)"
```

---

## Phase 3: Live Data Verification & Network Clients

### Task 3.1: API-Football smoke test (MANDATORY verify-early gate)

**Files:**
- Create: `scripts/smoke_test_apifootball.py`

This is the spec's section 3.4 gate. It is a standalone script run manually with a real
free key. It does NOT get imported by the game. It prints, in ASCII only, whether the free
tier actually returns a live fixture + lineups + statistics for the current season.

- [ ] **Step 1: Create the script**

```python
# scripts/smoke_test_apifootball.py
"""Manual smoke test: confirm API-Football free tier serves live fixtures + lineups + stats.

Usage:
  set API_FOOTBALL_KEY in env, then:
  .venv/Scripts/python scripts/smoke_test_apifootball.py
ASCII output only.
"""
import json
import os
import sys
import urllib.request

BASE = "https://v3.football.api-sports.io"


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        print("FAIL: set API_FOOTBALL_KEY in the environment first")
        return 1

    print("=== API-Football free-tier smoke test ===")
    live = _get("/fixtures?live=all", key)
    errors = live.get("errors")
    if errors:
        print("API errors:", errors)
    count = live.get("results", 0)
    print(f"live fixtures returned: {count}")
    if not count:
        print("NOTE: no live matches right now OR free tier blocks current season.")
        print("Re-run during a live match to disambiguate.")
        return 2

    fixture = live["response"][0]
    fid = fixture["fixture"]["id"]
    print(f"sample fixture id: {fid}")

    lineups = _get(f"/fixtures/lineups?fixture={fid}", key)
    print(f"lineups results: {lineups.get('results', 0)} (errors: {lineups.get('errors')})")

    stats = _get(f"/fixtures/statistics?fixture={fid}", key)
    print(f"statistics results: {stats.get('results', 0)} (errors: {stats.get('errors')})")

    ok = lineups.get("results", 0) and stats.get("results", 0)
    print("RESULT:", "OK - free tier serves live lineups + stats" if ok
          else "FAIL - lineups or stats unavailable on free tier")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it (requires a real free key + a live match)**

Run:
```bash
API_FOOTBALL_KEY=your_key .venv/Scripts/python scripts/smoke_test_apifootball.py
```
Expected: prints `RESULT: OK ...` during a live match.

**DECISION GATE:** If RESULT is FAIL (free tier blocks current-season live data), STOP here
and switch the live path to the MockFeed: the UI uses `MockFeed` from canned matches for v1
and real-data integration is deferred. Record the outcome in `docs/log.md`. Do not build the
soccer network clients (Tasks 3.3-3.4) against an unverified source.

- [ ] **Step 3: Record the result in the log and commit the script**

Append to `log.md`: `YYYY-MM-DD | API-Football smoke test [OK|FAIL]: <one line> | scripts/smoke_test_apifootball.py`

```bash
git add scripts/smoke_test_apifootball.py log.md
git commit -m "feat: API-Football free-tier smoke test (verify-early gate)"
```

---

### Task 3.2: Reconcile adapter field names with smoke-test reality

**Files:**
- Modify: `src/game/normalize_soccer.py`, `assets/data/stats_menu.json` (only if smoke test revealed different field names)
- Create: `scripts/capture_fixtures.py`

- [ ] **Step 1: Create the fixture-capture script**

```python
# scripts/capture_fixtures.py
"""Capture real API-Football JSON into tests/fixtures/ for deterministic tests.

Usage: API_FOOTBALL_KEY=... .venv/Scripts/python scripts/capture_fixtures.py <fixture_id>
ASCII output only.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://v3.football.api-sports.io"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key or len(sys.argv) < 2:
        print("FAIL: need API_FOOTBALL_KEY and a fixture id argument")
        return 1
    fid = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path in [("apifootball_lineups_real", f"/fixtures/lineups?fixture={fid}"),
                       ("apifootball_statistics_real", f"/fixtures/statistics?fixture={fid}")]:
        data = _get(path, key)
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=2))
        print(f"OK wrote {name}.json ({data.get('results', 0)} results)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: If the smoke test revealed different field names or position codes, update `_STAT_FIELD` / `_POS_MAP` in `normalize_soccer.py` and `api_field` values in `stats_menu.json` to match, then re-run the adapter tests**

Run: `.venv/Scripts/pytest tests/test_normalize_soccer.py -v`
Expected: PASS (update fixtures if you adjusted field names).

- [ ] **Step 3: Commit**

```bash
git add scripts/capture_fixtures.py src/game/normalize_soccer.py assets/data/stats_menu.json
git commit -m "feat: fixture capture + reconcile adapter field names with live API"
```

---

### Task 3.3: Relay client (room/token/action — mirrors MULTIPLAYER/baseball_api.php)

**Files:**
- Create: `src/sync/relay_client.py`
- Create: `src/sync/__init__.py`
- Test: `tests/test_relay_client.py`

The relay uses the PROVEN endpoint shape from `MULTIPLAYER/baseball_api.php`: a query-string
`action`, an integer `room`, and a per-player `token`. Reads are `GET ?action=state&room=N&token=T`;
writes are `POST ?action=update&room=N&token=T` with a JSON body carrying a `type` field. The
client must work under pygbag (browser) where `urllib` is unavailable — transport is injectable
so tests hit no network and a fetch-based transport can be swapped in for the WASM build.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_relay_client.py
import asyncio
import json
from src.sync.relay_client import RelayClient


class _FakeTransport:
    def __init__(self):
        self.gets: list[str] = []
        self.posts: list[tuple[str, str]] = []

    async def get(self, url: str) -> str:
        self.gets.append(url)
        return json.dumps({"success": True, "phase": "playing", "current_turn": 2,
                           "seed": 424242, "my_player": 1})

    async def post(self, url: str, body: str) -> str:
        self.posts.append((url, body))
        return json.dumps({"success": True})


def test_join_uses_action_and_room():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.join(room=2))
    assert "action=join" in t.posts[0][0] and "room=2" in t.posts[0][0]


def test_get_state_passes_token_and_parses():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    state = asyncio.run(client.get_state(room=0, token="abc"))
    assert "action=state" in t.gets[0] and "token=abc" in t.gets[0]
    assert state["seed"] == 424242


def test_submit_window_sends_type_and_predictions():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.submit_window(room=0, token="abc", window=1,
                                     predictions=["corner:3", "shot:2"],
                                     active_id="sccr-1", use_power=True))
    body = t.posts[0][1]
    assert '"type": "window_submit"' in body
    assert "corner:3" in body and "sccr-1" in body


def test_submit_draft_and_score_event_have_distinct_types():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.submit_draft(room=0, token="abc", athlete_ids=["sccr-1"]))
    asyncio.run(client.submit_score_event(room=0, token="abc", code="0:1:for:1"))
    assert '"type": "draft_submit"' in t.posts[0][1]
    assert '"type": "score_event"' in t.posts[1][1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_relay_client.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/sync/__init__.py
```
```python
# src/sync/relay_client.py
"""Async client for the room/token/action PHP relay (php/soccer_api.php).

Mirrors the proven MULTIPLAYER/baseball_api.php transport: query-string action + room + token,
JSON POST bodies tagged with a "type" field. Transport is injectable for tests and for the
pygbag/WASM fetch backend.
"""
import json
from typing import Any, Protocol


class Transport(Protocol):
    async def get(self, url: str) -> str: ...
    async def post(self, url: str, body: str) -> str: ...


class UrllibTransport:
    """Desktop/test transport. In pygbag, swap for a fetch-based transport."""
    async def get(self, url: str) -> str:
        import urllib.request
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read().decode("utf-8")

    async def post(self, url: str, body: str) -> str:
        import urllib.request
        req = urllib.request.Request(url, data=body.encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")


class RelayClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 api_path: str = "/soccer_api.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = api_path
        self._t = transport or UrllibTransport()

    def _url(self, action: str, room: int, token: str = "") -> str:
        url = f"{self._base}{self._path}?action={action}&room={room}"
        return url + (f"&token={token}" if token else "")

    async def list_rooms(self) -> dict[str, Any]:
        return json.loads(await self._t.get(f"{self._base}{self._path}?action=list"))

    async def join(self, room: int) -> dict[str, Any]:
        return json.loads(await self._t.post(self._url("join", room), "{}"))

    async def get_state(self, room: int, token: str) -> dict[str, Any]:
        return json.loads(await self._t.get(self._url("state", room, token)))

    async def heartbeat(self, room: int, token: str) -> dict[str, Any]:
        return json.loads(await self._t.post(self._url("heartbeat", room, token), "{}"))

    async def _update(self, room: int, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload)
        return json.loads(await self._t.post(self._url("update", room, token), body))

    async def submit_draft(self, room: int, token: str,
                           athlete_ids: list[str]) -> dict[str, Any]:
        return await self._update(room, token,
                                  {"type": "draft_submit", "athlete_ids": athlete_ids})

    async def submit_window(self, room: int, token: str, window: int,
                            predictions: list[str], active_id: str,
                            use_power: bool) -> dict[str, Any]:
        return await self._update(room, token, {
            "type": "window_submit", "window": window, "predictions": predictions,
            "active_id": active_id, "use_power": use_power,
        })

    async def submit_score_event(self, room: int, token: str, code: str) -> dict[str, Any]:
        return await self._update(room, token, {"type": "score_event", "code": code})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_relay_client.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sync/__init__.py src/sync/relay_client.py tests/test_relay_client.py
git commit -m "feat: room/token/action relay client (mirrors baseball_api.php)"
```

---

### Task 3.4: Feed client + session state

**Files:**
- Create: `src/sync/feed_client.py`
- Create: `src/sync/session_state.py`
- Test: `tests/test_session_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_state.py
from src.sync.session_state import SessionState


def test_window_for_minute_uses_window_seconds():
    st = SessionState(room=0, token="t", seed=123, slot=0)
    # window_seconds=300 -> 5-min windows; minute 0-4 -> window 1, 5-9 -> window 2
    assert st.window_for_minute(0) == 1
    assert st.window_for_minute(4) == 1
    assert st.window_for_minute(5) == 2


def test_record_and_aggregate_score_events():
    st = SessionState(room=0, token="t", seed=123, slot=0)
    st.add_score_event("0:1:for:1")
    st.add_score_event("1:1:against:1")
    team, opp = st.shared_score()
    assert team == 1 and opp == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_session_state.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# src/sync/session_state.py
"""Local session bookkeeping: room/token identity, window math, known score events.

slot (0/1) is derived from the relay's my_player (1/2) and is used when stamping this
client's own score-event codes. seed comes once from the room and feeds the shared RNG.
"""
from src.game.scoring import aggregate
from src.utils.constants import CONFIG


class SessionState:
    def __init__(self, room: int, token: str, seed: int, slot: int) -> None:
        self.room = room
        self.token = token
        self.seed = seed
        self.slot = slot
        self.score_events: list[str] = []
        self._window_minutes = CONFIG["game"]["window_seconds"] // 60

    def window_for_minute(self, minute: int) -> int:
        return minute // self._window_minutes + 1

    def add_score_event(self, code: str) -> None:
        if code not in self.score_events:
            self.score_events.append(code)

    def shared_score(self) -> tuple[int, int]:
        return aggregate(self.score_events)
```

```python
# src/sync/feed_client.py
"""Fetch the cached feed snapshot from the PHP relay (server-side proxy of API-Football).

The relay caches per fixture so both clients share one upstream quota draw; the client just
asks for a fixture id.
"""
import json
from typing import Any
from src.sync.relay_client import Transport, UrllibTransport


class FeedClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 feed_path: str = "/feed_cache.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = feed_path
        self._t = transport or UrllibTransport()

    async def get_feed(self, fixture_id: int) -> dict[str, Any]:
        url = f"{self._base}{self._path}?fixture={fixture_id}"
        return json.loads(await self._t.get(url))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_session_state.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sync/feed_client.py src/sync/session_state.py tests/test_session_state.py
git commit -m "feat: feed client and local session-state bookkeeping"
```

---

## Phase 4: PHP Relay (adapted from MULTIPLAYER/baseball_api.php)

The proven `MULTIPLAYER/baseball_api.php` already solves room management, token auth,
heartbeat/timeout, file-locked writes, self-cleanup, and — critically — the BLIND REVEAL via
`get_revealed_turns()` (an opponent's turn is only revealed once you've submitted the same
turn). Phase 4 ADAPTS that file: keep all transport mechanics; swap baseball phases
(`team_select`/`pitcher_select`) for soccer phases (`draft`/`playing`), swap
`turn_submit`/`placements` for `window_submit`/`predictions`, and add a `score_event` append.
Co-op changes only semantics (both players build one shared team score), not transport.

Read `MULTIPLAYER/baseball_api.php` before starting this phase. PHP is verified by `php -l`
+ manual curl, not unit tests.

### Task 4.1: soccer_api.php (room/token relay with soccer phases + blind window reveal)

**Files:**
- Create: `php/soccer_api.php`
- Create: `php/.htaccess` (copy of `MULTIPLAYER/.htaccess`)
- Create: `php/game_rooms/.htaccess` (copy of `MULTIPLAYER/game_rooms/.htaccess`)
- Create: `php/README.md`

- [ ] **Step 1: Copy the two `.htaccess` files verbatim from MULTIPLAYER**

Run:
```bash
mkdir -p php/game_rooms
cp MULTIPLAYER/.htaccess php/.htaccess
cp MULTIPLAYER/game_rooms/.htaccess php/game_rooms/.htaccess
```
Expected: both files exist under `php/`.

- [ ] **Step 2: Create `php/soccer_api.php` (adapted from baseball_api.php)**

```php
<?php
/**
 * PJAB Coop Soccer - Multiplayer Relay
 * Adapted from baseball_api.php. Co-op: both players build one shared team score.
 *
 * Endpoints:
 *   GET  ?action=list                       - list rooms
 *   POST ?action=join&room=N                - join/create room N
 *   GET  ?action=state&room=N&token=XXX     - get game state (blind-revealed)
 *   POST ?action=update&room=N&token=XXX    - update (JSON body with "type")
 *   POST ?action=heartbeat&room=N&token=XXX - keep alive
 *   POST ?action=leave&room=N&token=XXX     - leave
 *
 * update types: draft_submit, window_submit, score_event, game_result
 */
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }

define('ROOMS_DIR', __DIR__ . '/game_rooms/');
define('MAX_ROOMS', 4);
define('HEARTBEAT_TIMEOUT', 30);
define('GAME_TIMEOUT', 3600);
define('CLEANUP_AGE', 300);

if (!is_dir(ROOMS_DIR)) { mkdir(ROOMS_DIR, 0755, true); }

function generate_token(): string { return bin2hex(random_bytes(8)); }
function get_room_path(int $room): string { return ROOMS_DIR . "room_$room.json"; }

function read_room(int $room): ?array {
    $path = get_room_path($room);
    if (!file_exists($path)) { return null; }
    $c = file_get_contents($path);
    return $c === false ? null : json_decode($c, true);
}

function write_room(int $room, array $data): bool {
    $data['updated_at'] = time();
    return file_put_contents(get_room_path($room),
        json_encode($data, JSON_PRETTY_PRINT), LOCK_EX) !== false;
}

function delete_room(int $room): bool {
    $path = get_room_path($room);
    return file_exists($path) ? unlink($path) : true;
}

function create_empty_room(int $room): array {
    return [
        'room_id' => $room, 'status' => 'empty',
        'created_at' => time(), 'updated_at' => time(),
        'seed' => random_int(100000, 999999),
        'p1' => null, 'p2' => null,
        'current_phase' => 'waiting', 'current_window' => 0,
        'window_started_at' => null,
        'score_events' => [], 'final_score' => null,
    ];
}

function create_player(string $token): array {
    return [
        'token' => $token, 'joined_at' => time(), 'last_heartbeat' => time(),
        'connected' => true, 'athlete_ids' => null,
        'windows_submitted' => [], 'current_window_ready' => false,
    ];
}

function check_player_timeouts(array &$room): bool {
    $changed = false; $now = time();
    foreach (['p1', 'p2'] as $p) {
        if (isset($room[$p]) && $room[$p] !== null && $room[$p]['connected']) {
            if ($now - $room[$p]['last_heartbeat'] > HEARTBEAT_TIMEOUT) {
                $room[$p]['connected'] = false; $changed = true;
            }
        }
    }
    return $changed;
}

function cleanup_old_rooms(): void {
    $now = time();
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $d = read_room($i);
        if (!$d) { continue; }
        $age = $now - $d['updated_at'];
        if ($d['status'] === 'game_over' && $age > CLEANUP_AGE) { delete_room($i); continue; }
        if ($age > GAME_TIMEOUT) { delete_room($i); continue; }
        if ($d['status'] === 'waiting' && $age > 300) { delete_room($i); continue; }
    }
}

function respond(array $data, int $code = 200): void {
    http_response_code($code); echo json_encode($data); exit;
}
function fail(string $msg, int $code = 400): void {
    respond(['error' => $msg, 'success' => false], $code);
}

// Blind reveal: only show an opponent window I have also submitted.
function get_revealed_windows(array $room, int $my_player): array {
    $opp = $my_player === 1 ? 'p2' : 'p1';
    $me = $my_player === 1 ? 'p1' : 'p2';
    if (!isset($room[$opp]) || $room[$opp] === null) { return []; }
    $revealed = [];
    $mine = $room[$me]['windows_submitted'] ?? [];
    $theirs = $room[$opp]['windows_submitted'] ?? [];
    foreach ($theirs as $w => $payload) {
        if (isset($mine[$w])) { $revealed[$w] = $payload; }
    }
    return $revealed;
}

function action_list(): void {
    cleanup_old_rooms();
    $rooms = [];
    for ($i = 0; $i < MAX_ROOMS; $i++) {
        $d = read_room($i);
        if ($d) {
            check_player_timeouts($d); write_room($i, $d);
            $rooms[] = [
                'room_id' => $i, 'status' => $d['status'], 'phase' => $d['current_phase'],
                'p1_connected' => isset($d['p1']) && $d['p1'] !== null && $d['p1']['connected'],
                'p2_connected' => isset($d['p2']) && $d['p2'] !== null && $d['p2']['connected'],
                'current_window' => $d['current_window'],
                'age_seconds' => time() - $d['created_at'],
            ];
        } else {
            $rooms[] = ['room_id' => $i, 'status' => 'empty', 'phase' => null,
                        'p1_connected' => false, 'p2_connected' => false,
                        'current_window' => 0, 'age_seconds' => 0];
        }
    }
    respond(['success' => true, 'rooms' => $rooms, 'server_time' => time()]);
}

function action_join(int $room): void {
    if ($room < 0 || $room >= MAX_ROOMS) { fail('Invalid room number'); }
    $d = read_room($room);
    $token = generate_token();

    if (!$d || $d['status'] === 'empty' || $d['status'] === 'game_over') {
        $d = create_empty_room($room);
        $d['status'] = 'waiting'; $d['current_phase'] = 'waiting';
        $d['p1'] = create_player($token);
        write_room($room, $d);
        respond(['success' => true, 'token' => $token, 'player' => 1,
                 'seed' => $d['seed'], 'message' => 'Created room. Waiting for partner...']);
    }

    check_player_timeouts($d);
    if (in_array($d['current_phase'], ['playing', 'resolving'])) {
        fail('Game in progress. Try another room.', 409);
    }
    $p2_exists = isset($d['p2']) && $d['p2'] !== null;
    if (!$p2_exists) {
        $d['p2'] = create_player($token);
        $d['status'] = 'active'; $d['current_phase'] = 'draft';
        write_room($room, $d);
        respond(['success' => true, 'token' => $token, 'player' => 2,
                 'seed' => $d['seed'], 'message' => 'Joined as Player 2. Draft your six!']);
    }
    fail('Room is full. Try another room.', 409);
}

function resolve_player(array $d, string $token): array {
    if (isset($d['p1']) && $d['p1'] !== null && $d['p1']['token'] === $token) {
        return [1, 'p1'];
    }
    if (isset($d['p2']) && $d['p2'] !== null && $d['p2']['token'] === $token) {
        return [2, 'p2'];
    }
    fail('Invalid token', 403);
}

function action_state(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $me_key] = resolve_player($d, $token);
    check_player_timeouts($d); write_room($room, $d);
    $opp_key = $player === 1 ? 'p2' : 'p1';
    $me = $d[$me_key]; $opp = $d[$opp_key];

    respond([
        'success' => true, 'room_id' => $room, 'status' => $d['status'],
        'phase' => $d['current_phase'], 'seed' => $d['seed'],
        'current_window' => $d['current_window'],
        'window_started_at' => $d['window_started_at'],
        'my_player' => $player, 'score_events' => $d['score_events'] ?? [],
        'final_score' => $d['final_score'], 'server_time' => time(),
        'me' => [
            'connected' => $me['connected'] ?? false,
            'athlete_ids' => $me['athlete_ids'] ?? null,
            'current_window_ready' => $me['current_window_ready'] ?? false,
            'windows_submitted' => $me['windows_submitted'] ?? [],
        ],
        'opponent' => [
            'connected' => $opp['connected'] ?? false,
            'athlete_ids' => $opp['athlete_ids'] ?? null,
            'current_window_ready' => $opp['current_window_ready'] ?? false,
            'windows_submitted' => get_revealed_windows($d, $player),
        ],
    ]);
}

function action_update(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $pk] = resolve_player($d, $token);
    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['type'])) { fail('Body must be JSON with "type"'); }

    $d[$pk]['last_heartbeat'] = time();
    $d[$pk]['connected'] = true;

    switch ($input['type']) {
        case 'draft_submit':
            if ($d['current_phase'] !== 'draft') { fail('Not in draft phase'); }
            if (!isset($input['athlete_ids']) || !is_array($input['athlete_ids'])) {
                fail('Missing athlete_ids');
            }
            $d[$pk]['athlete_ids'] = array_map('strval', $input['athlete_ids']);
            $p1r = isset($d['p1']['athlete_ids']) && $d['p1']['athlete_ids'] !== null;
            $p2r = isset($d['p2']['athlete_ids']) && $d['p2']['athlete_ids'] !== null;
            if ($p1r && $p2r) {
                $d['current_phase'] = 'playing';
                $d['current_window'] = 1;
                $d['window_started_at'] = time();
            }
            break;

        case 'window_submit':
            if ($d['current_phase'] !== 'playing') { fail('Not in playing phase'); }
            if (!isset($input['window']) || !isset($input['predictions'])) {
                fail('Missing window or predictions');
            }
            $w = strval(intval($input['window']));
            $d[$pk]['windows_submitted'][$w] = [
                'predictions' => $input['predictions'],
                'active_id' => strval($input['active_id'] ?? ''),
                'use_power' => (bool)($input['use_power'] ?? false),
            ];
            $d[$pk]['current_window_ready'] = true;
            $p1r = $d['p1']['current_window_ready'] ?? false;
            $p2r = $d['p2']['current_window_ready'] ?? false;
            if ($p1r && $p2r) {
                $d['p1']['current_window_ready'] = false;
                $d['p2']['current_window_ready'] = false;
                $d['current_window']++;
                $d['window_started_at'] = time();
            }
            break;

        case 'score_event':
            if (!isset($input['code'])) { fail('Missing code'); }
            $code = strval($input['code']);
            if (!in_array($code, $d['score_events'], true)) {
                $d['score_events'][] = $code;
            }
            break;

        case 'game_result':
            $d['current_phase'] = 'game_over';
            $d['status'] = 'game_over';
            $d['final_score'] = $input['final_score'] ?? [0, 0];
            break;

        default:
            fail('Unknown update type: ' . $input['type']);
    }

    write_room($room, $d);
    respond(['success' => true, 'phase' => $d['current_phase'],
             'current_window' => $d['current_window']]);
}

function action_heartbeat(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { fail('Room not found', 404); }
    [$player, $pk] = resolve_player($d, $token);
    $d[$pk]['last_heartbeat'] = time();
    $d[$pk]['connected'] = true;
    check_player_timeouts($d); write_room($room, $d);
    respond(['success' => true, 'server_time' => time()]);
}

function action_leave(int $room, string $token): void {
    $d = read_room($room);
    if (!$d) { respond(['success' => true, 'message' => 'Room already empty']); }
    [$player, $pk] = resolve_player($d, $token);
    $d[$pk]['connected'] = false;
    $p1c = isset($d['p1']) && $d['p1'] !== null && $d['p1']['connected'];
    $p2c = isset($d['p2']) && $d['p2'] !== null && $d['p2']['connected'];
    if (!$p1c && !$p2c) {
        $d['status'] = 'game_over'; $d['current_phase'] = 'game_over';
    }
    write_room($room, $d);
    respond(['success' => true, 'message' => 'Left room']);
}

$action = $_GET['action'] ?? '';
$room = isset($_GET['room']) ? intval($_GET['room']) : -1;
$token = $_GET['token'] ?? '';

switch ($action) {
    case 'list': action_list(); break;
    case 'join': action_join($room); break;
    case 'state': action_state($room, $token); break;
    case 'update': action_update($room, $token); break;
    case 'heartbeat': action_heartbeat($room, $token); break;
    case 'leave': action_leave($room, $token); break;
    case 'reset':
        if ($room >= 0 && $room < MAX_ROOMS) {
            delete_room($room);
            respond(['success' => true, 'message' => "Room $room reset"]);
        }
        fail('Invalid room number');
        break;
    case '':
        respond(['name' => 'PJAB Coop Soccer Relay', 'version' => '1.0.0',
                 'endpoints' => ['list', 'join', 'state', 'update', 'heartbeat', 'leave']]);
        break;
    default: fail("Unknown action: $action");
}
```

- [ ] **Step 3: Create `php/README.md`**

```markdown
# PHP Relay -- PJAB Coop Soccer Game

Adapted from MULTIPLAYER/baseball_api.php. Deploy `soccer_api.php`, `feed_cache.php`, and the
two `.htaccess` files to `drpeterjamieson.com/game/` via SFTP. A writable `game_rooms/`
directory sits beside them (auto-created; the `.htaccess` there denies direct JSON access).

## soccer_api.php (room/token/action)
- GET  `?action=list`                      -> room summaries
- POST `?action=join&room=N`               -> `{token, player, seed}`
- GET  `?action=state&room=N&token=T`      -> blind-revealed game state
- POST `?action=update&room=N&token=T`     -> body `{type, ...}`:
  - `{type:"draft_submit", athlete_ids:[...]}`   (phase: draft)
  - `{type:"window_submit", window, predictions:[...], active_id, use_power}` (phase: playing)
  - `{type:"score_event", code:"slot:window:side:scored"}`
  - `{type:"game_result", final_score:[team, opp]}`
- POST `?action=heartbeat&room=N&token=T`  -> keep alive (30s timeout)
- POST `?action=leave&room=N&token=T`      -> disconnect

Blind reveal: `state` only returns an opponent's window once you have submitted the same
window number. Rooms self-clean (completed after 5 min, stale after 1 h).

## feed_cache.php
- GET `?fixture=ID` -> cached API-Football snapshot, refreshed at most once per CACHE_TTL.
  API key read from `apifootball_key.txt` (NOT web-readable).

Keep payloads small: only drafts, window predictions, and score-event codes are stored.
```

- [ ] **Step 4: Lint the PHP syntax (if php CLI available)**

Run: `php -l php/soccer_api.php` (if PHP installed) — Expected: `No syntax errors detected`.
If PHP is not installed locally, skip; it is validated on deploy.

- [ ] **Step 5: Commit**

```bash
git add php/soccer_api.php php/.htaccess php/game_rooms/.htaccess php/README.md
git commit -m "feat: soccer relay adapted from baseball_api.php (rooms, tokens, blind reveal)"
```

---

### Task 4.2: feed_cache.php (API-Football server-side cache)

**Files:**
- Create: `php/feed_cache.php`

Room self-cleanup is handled inside `soccer_api.php` (no separate cleanup cron needed); this
task adds only the feed proxy/cache.

- [ ] **Step 1: Create `php/feed_cache.php`**

```php
<?php
// feed_cache.php -- server-side proxy + cache of API-Football, served to both clients.
// Refreshes at most once per CACHE_TTL seconds so the shared free-tier quota is not doubled.
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$CACHE_TTL = 110; // seconds; just under the client 120s poll cadence
$cacheFile = __DIR__ . '/feed_cache.json';
$keyFile = __DIR__ . '/apifootball_key.txt'; // one line, NOT web-readable

$fixture = preg_replace('/[^0-9]/', '', $_GET['fixture'] ?? '');

if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < $CACHE_TTL)) {
    echo file_get_contents($cacheFile);
    exit;
}
if (!file_exists($keyFile) || $fixture === '') {
    http_response_code(503);
    echo '{"error":"feed unavailable"}';
    exit;
}
$key = trim(file_get_contents($keyFile));
$base = "https://v3.football.api-sports.io";
$headers = ["x-apisports-key: $key"];

function api_get($url, $headers) {
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    $out = curl_exec($ch);
    curl_close($ch);
    return $out ? json_decode($out, true) : null;
}

$snapshot = [
    "lineups"    => api_get("$base/fixtures/lineups?fixture=$fixture", $headers),
    "statistics" => api_get("$base/fixtures/statistics?fixture=$fixture", $headers),
    "fixture"    => api_get("$base/fixtures?id=$fixture", $headers),
    "cached_at"  => time(),
];
file_put_contents($cacheFile, json_encode($snapshot), LOCK_EX);
echo json_encode($snapshot);
```

- [ ] **Step 2: Lint (if php available)**

Run: `php -l php/feed_cache.php`
Expected: `No syntax errors detected` (skip if no PHP CLI).

- [ ] **Step 3: Commit**

```bash
git add php/feed_cache.php
git commit -m "feat: PHP feed cache proxy for API-Football"
```

---

## Phase 5: Mobile pygame UI

UI is iterative/visual; these tasks give concrete, runnable starting code. Verify each by
launching the game, not by unit tests (UI is outside the `src/game/` test boundary).

### Task 5.1: Mobile widgets (button, card, meter bar)

**Files:**
- Create: `src/ui/widgets.py`

- [ ] **Step 1: Create `src/ui/widgets.py`**

```python
# src/ui/widgets.py
"""Mobile-friendly pygame widgets: large touch targets. All pygame lives in src/ui/."""
import pygame
from src.utils.constants import CONFIG

_C = CONFIG["colors"]


class Button:
    def __init__(self, rect: pygame.Rect, label: str) -> None:
        self.rect = rect
        self.label = label

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=12)
        pygame.draw.rect(surface, _C["border"], self.rect, width=2, border_radius=12)
        text = font.render(self.label, True, _C["text"])
        surface.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


class MeterBar:
    def __init__(self, rect: pygame.Rect, color: list[int]) -> None:
        self.rect = rect
        self.color = color

    def draw(self, surface: pygame.Surface, value: int, threshold: int) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=8)
        frac = 0 if threshold <= 0 else max(0.0, min(1.0, value / threshold))
        fill = self.rect.copy()
        fill.width = int(self.rect.width * frac)
        pygame.draw.rect(surface, self.color, fill, border_radius=8)


def athlete_card(surface: pygame.Surface, rect: pygame.Rect,
                 font: pygame.font.Font, name: str, archetype: str,
                 stars: int, selected: bool) -> None:
    bg = _C["accent"] if selected else _C["surface"]
    pygame.draw.rect(surface, bg, rect, border_radius=10)
    pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=10)
    surface.blit(font.render(name[:16], True, _C["white"]), (rect.x + 8, rect.y + 6))
    surface.blit(font.render(f"{archetype}  {'*' * stars}", True, _C["text_dim"]),
                 (rect.x + 8, rect.y + 30))
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/widgets.py
git commit -m "feat: mobile pygame widgets"
```

---

### Task 5.2: App state machine + screens skeleton

**Files:**
- Create: `src/ui/app.py`
- Create: `src/ui/screens/__init__.py`
- Create: `src/ui/screens/base.py`

- [ ] **Step 1: Create `src/ui/screens/base.py`**

```python
# src/ui/screens/base.py
"""Base screen for the async state machine."""
import pygame


class Screen:
    def __init__(self, app: "object") -> None:
        self.app = app

    def handle(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
```

- [ ] **Step 2: Create `src/ui/screens/__init__.py`** (empty)

```python
```

- [ ] **Step 3: Create `src/ui/app.py`**

```python
# src/ui/app.py
"""Async pygame app + screen state machine. pygbag entry path."""
import asyncio
import pygame
from src.utils.constants import CONFIG

_D = CONFIG["display"]
_C = CONFIG["colors"]


class App:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((_D["width"], _D["height"]))
        pygame.display.set_caption(_D["title"])
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 22)
        self.running = True
        self.current = None  # set by set_screen

    def set_screen(self, screen) -> None:
        self.current = screen

    async def run(self) -> None:
        while self.running:
            dt = self.clock.tick(_D["fps"]) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif self.current is not None:
                    self.current.handle(event)
            if self.current is not None:
                self.current.update(dt)
            self.screen.fill(_C["background"])
            if self.current is not None:
                self.current.draw(self.screen)
            pygame.display.flip()
            await asyncio.sleep(0)
```

- [ ] **Step 4: Verify it imports**

Run: `.venv/Scripts/python -c "from src.ui.app import App; print('OK')"`
Expected: prints `OK` (no display created on import).

- [ ] **Step 5: Commit**

```bash
git add src/ui/app.py src/ui/screens/__init__.py src/ui/screens/base.py
git commit -m "feat: async app state machine and screen base"
```

---

### Task 5.3: Draft screen

**Files:**
- Create: `src/ui/screens/draft_screen.py`

- [ ] **Step 1: Create `src/ui/screens/draft_screen.py`**

```python
# src/ui/screens/draft_screen.py
"""Draft screen: tap athlete cards to build a 6-athlete hand from the pool."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import athlete_card, Button
from src.game.athlete import DraftedAthlete
from src.utils.constants import CONFIG

_ROSTER_SIZE = CONFIG["game"]["roster_size"]


class DraftScreen(Screen):
    def __init__(self, app, pool: list[DraftedAthlete], on_lock) -> None:
        super().__init__(app)
        self.pool = pool
        self.on_lock = on_lock
        self.selected: list[str] = []
        self.scroll = 0
        self.lock_btn = Button(pygame.Rect(20, app.screen.get_height() - 70,
                                           app.screen.get_width() - 40, 50),
                               f"Lock {len(self.selected)}/{_ROSTER_SIZE}")

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.lock_btn.hit(event.pos) and len(self.selected) == _ROSTER_SIZE:
                self.on_lock(list(self.selected))
                return
            idx = self._card_at(event.pos)
            if idx is not None:
                aid = self.pool[idx].athlete_id
                if aid in self.selected:
                    self.selected.remove(aid)
                elif len(self.selected) < _ROSTER_SIZE:
                    self.selected.append(aid)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 40)

    def _card_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(20, 20 + i * 70 - self.scroll, self.app.screen.get_width() - 40, 60)

    def _card_at(self, pos):
        for i in range(len(self.pool)):
            if self._card_rect(i).collidepoint(pos):
                return i
        return None

    def update(self, dt: float) -> None:
        self.lock_btn.label = f"Lock {len(self.selected)}/{_ROSTER_SIZE}"

    def draw(self, surface: pygame.Surface) -> None:
        for i, ath in enumerate(self.pool):
            r = self._card_rect(i)
            if r.bottom < 0 or r.top > surface.get_height():
                continue
            athlete_card(surface, r, self.app.font, ath.name, ath.archetype,
                         ath.stars, ath.athlete_id in self.selected)
        self.lock_btn.draw(surface, self.app.font)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/screens/draft_screen.py
git commit -m "feat: mobile draft screen"
```

---

### Task 5.4: Predict screen

**Files:**
- Create: `src/ui/screens/predict_screen.py`

- [ ] **Step 1: Create `src/ui/screens/predict_screen.py`**

```python
# src/ui/screens/predict_screen.py
"""Predict screen: choose <=2 stat lines (+/- to set the integer), pick active player, toggle power."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, athlete_card
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.utils.constants import CONFIG, load_data

_MAX = CONFIG["game"]["max_predictions_per_window"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]


class PredictScreen(Screen):
    def __init__(self, app, available: list[DraftedAthlete], on_submit) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.lines: dict[str, int] = {s["code"]: s["default_line"] for s in _STATS}
        self.chosen: list[str] = []
        self.active_id: str | None = None
        self.use_power = False
        w = app.screen.get_width()
        self.submit_btn = Button(pygame.Rect(20, app.screen.get_height() - 60, w - 40, 46),
                                 "Lock predictions")

    def handle(self, event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        x, y = event.pos
        for i, s in enumerate(_STATS):
            row_y = 20 + i * 56
            if row_y <= y <= row_y + 48:
                if x > self.app.screen.get_width() - 60:      # plus
                    self.lines[s["code"]] += 1
                elif x > self.app.screen.get_width() - 120:   # minus
                    self.lines[s["code"]] = max(0, self.lines[s["code"]] - 1)
                else:                                          # toggle chosen
                    self._toggle(s["code"])
                return
        # active player row
        base_y = 20 + len(_STATS) * 56 + 10
        for j, ath in enumerate(self.available):
            r = pygame.Rect(20, base_y + j * 64, self.app.screen.get_width() - 40, 56)
            if r.collidepoint(event.pos):
                self.active_id = ath.athlete_id
                return
        if self.submit_btn.hit(event.pos) and self.chosen and self.active_id:
            preds = [Prediction(c, self.lines[c]) for c in self.chosen]
            self.on_submit(preds, self.active_id, self.use_power)

    def _toggle(self, code: str) -> None:
        if code in self.chosen:
            self.chosen.remove(code)
        elif len(self.chosen) < _MAX:
            self.chosen.append(code)

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        f = self.app.font
        c = CONFIG["colors"]
        for i, s in enumerate(_STATS):
            row = pygame.Rect(20, 20 + i * 56, surface.get_width() - 40, 48)
            sel = s["code"] in self.chosen
            pygame.draw.rect(surface, c["accent"] if sel else c["surface"], row, border_radius=8)
            surface.blit(f.render(f"{s['label']}: {self.lines[s['code']]}", True, c["white"]),
                         (row.x + 8, row.y + 12))
            surface.blit(f.render("-", True, c["white"]), (row.right - 110, row.y + 10))
            surface.blit(f.render("+", True, c["white"]), (row.right - 48, row.y + 10))
        base_y = 20 + len(_STATS) * 56 + 10
        for j, ath in enumerate(self.available):
            r = pygame.Rect(20, base_y + j * 64, surface.get_width() - 40, 56)
            athlete_card(surface, r, f, ath.name, ath.archetype, ath.stars,
                         ath.athlete_id == self.active_id)
        self.submit_btn.draw(surface, f)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/screens/predict_screen.py
git commit -m "feat: mobile predict screen"
```

---

### Task 5.5: Watch / reveal / final screens

**Files:**
- Create: `src/ui/screens/status_screens.py`

- [ ] **Step 1: Create `src/ui/screens/status_screens.py`**

```python
# src/ui/screens/status_screens.py
"""Watch (waiting), Reveal (window result), and Final (full-time) screens."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import MeterBar
from src.utils.constants import CONFIG

_C = CONFIG["colors"]
_M = CONFIG["meter"]


class WatchScreen(Screen):
    def __init__(self, app, get_state) -> None:
        super().__init__(app)
        self.get_state = get_state  # callable -> dict(team, opp, success, concede, window, clock)
        w = app.screen.get_width()
        self.success_bar = MeterBar(pygame.Rect(20, 200, w - 40, 24), _C["green"])
        self.concede_bar = MeterBar(pygame.Rect(20, 260, w - 40, 24), _C["red"])

    def handle(self, event): ...
    def update(self, dt): ...

    def draw(self, surface: pygame.Surface) -> None:
        s = self.get_state()
        f = self.app.font
        surface.blit(f.render(f"Window {s['window']}   {s['clock']}", True, _C["text"]), (20, 40))
        big = pygame.font.SysFont("arial", 56)
        surface.blit(big.render(f"{s['team']} - {s['opp']}", True, _C["white"]), (20, 90))
        surface.blit(f.render("Attack", True, _C["text_dim"]), (20, 176))
        self.success_bar.draw(surface, s["success"], _M["success_threshold"])
        surface.blit(f.render("Danger", True, _C["text_dim"]), (20, 236))
        self.concede_bar.draw(surface, s["concede"], _M["concede_threshold"])


class RevealScreen(Screen):
    def __init__(self, app, lines: list[str], on_continue) -> None:
        super().__init__(app)
        self.lines = lines
        self.on_continue = on_continue

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt): ...

    def draw(self, surface: pygame.Surface) -> None:
        f = self.app.font
        for i, line in enumerate(self.lines):
            surface.blit(f.render(line, True, _C["text"]), (20, 60 + i * 32))
        surface.blit(f.render("tap to continue", True, _C["text_dim"]),
                     (20, surface.get_height() - 50))


class FinalScreen(Screen):
    def __init__(self, app, team: int, opp: int, real_line: str | None) -> None:
        super().__init__(app)
        self.team, self.opp, self.real_line = team, opp, real_line

    def handle(self, event): ...
    def update(self, dt): ...

    def draw(self, surface: pygame.Surface) -> None:
        big = pygame.font.SysFont("arial", 48)
        surface.blit(big.render("Full Time", True, _C["white"]), (20, 80))
        surface.blit(big.render(f"You {self.team} - {self.opp} Opp", True, _C["accent"]),
                     (20, 150))
        if self.real_line:
            surface.blit(self.app.font.render(self.real_line, True, _C["text_dim"]), (20, 230))
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/screens/status_screens.py
git commit -m "feat: watch, reveal, and final screens"
```

---

### Task 5.6: Wire the entry point with a mock-feed demo flow

**Files:**
- Modify: `src/main.py`
- Modify: `main.py` (web entry)
- Create: `src/ui/demo_flow.py`

This wires a self-contained, playable single-device demo using `MockFeed` so the loop is
verifiable end-to-end without the relay or live API. Multi-device sync is layered on after
the demo flow is confirmed playable.

- [ ] **Step 1: Create `src/ui/demo_flow.py`**

```python
# src/ui/demo_flow.py
"""Single-device demo: MockFeed + one GameSession, walking draft -> predict -> watch -> final."""
import random
from src.game.mock_feed import MockFeed
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.predict_screen import PredictScreen
from src.ui.screens.status_screens import WatchScreen, RevealScreen, FinalScreen


def _demo_pool() -> list[DraftedAthlete]:
    rows = [("sccr-1", "A. Davies", "Defender"), ("sccr-2", "J. David", "Attacker"),
            ("sccr-3", "S. Eustaquio", "Midfielder"), ("sccr-4", "M. Crepeau", "Goalkeeper"),
            ("sccr-5", "T. Buchanan", "Defender"), ("sccr-6", "C. Larin", "Attacker"),
            ("sccr-7", "I. Koné", "Midfielder"), ("sccr-8", "A. Hernandez", "Defender"),
            ("sccr-9", "L. Brym", "Attacker"), ("sccr-10", "M. Kone", "Midfielder")]
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="Canada", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _demo_script() -> dict:
    return {
        "status_by_minute": [(0, "live"), (15, "finished")],
        "snapshots": [
            {"minute": 0,  "stats": {"corner_kicks": 0, "shots_on_goal": 0, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 5,  "stats": {"corner_kicks": 3, "shots_on_goal": 2, "goalkeeper_saves": 2, "goals": 0, "cards": 1}},
            {"minute": 10, "stats": {"corner_kicks": 6, "shots_on_goal": 5, "goalkeeper_saves": 3, "goals": 1, "cards": 1}},
            {"minute": 15, "stats": {"corner_kicks": 8, "shots_on_goal": 7, "goalkeeper_saves": 5, "goals": 2, "cards": 2}},
        ],
    }


def start(app) -> None:
    pool = _demo_pool()
    feed = MockFeed(_demo_script())
    state = {"window": 1, "minute": 0}

    def after_draft(selected: list[str]) -> None:
        hand = [a for a in pool if a.athlete_id in selected]
        session = GameSession(slot=0, roster=Roster(hand), pool=pool, rng=random.Random(99))
        score_codes: list[str] = []
        _run_window(app, feed, pool, session, state, score_codes)

    app.set_screen(DraftScreen(app, pool, after_draft))


def _stat_deltas(feed: MockFeed, start_min: int, end_min: int) -> dict[str, int]:
    a = feed.snapshot_at(start_min)
    b = feed.snapshot_at(end_min)
    keys = set(a.stats) | set(b.stats)
    return {k.replace("corner_kicks", "corner").replace("shots_on_goal", "shot")
             .replace("goalkeeper_saves", "save"): b.delta(a, k) for k in keys}


def _run_window(app, feed, pool, session, state, score_codes) -> None:
    minute = state["minute"]
    available = session.roster.available()

    def after_predict(preds, active_id, use_power) -> None:
        end_min = minute + 5
        actuals = _stat_deltas(feed, minute, end_min)
        res = session.resolve_window(window=state["window"], predictions=preds,
                                     active_id=active_id, use_power=use_power, actuals=actuals)
        for ev in res.score_events:
            score_codes.append(ev.to_code())
        team, opp = aggregate(score_codes)
        lines = [f"Window {state['window']} resolved.",
                 f"Attack meter: {session.success_meter.value}",
                 f"Danger meter: {session.concede_meter.value}",
                 f"Score: you {team} - {opp} opp"]
        for ev in res.score_events:
            lines.append(("GOAL!" if ev.scored and ev.side == "for" else
                          "CONCEDED!" if ev.scored else "shot missed"))

        def cont() -> None:
            state["minute"] = end_min
            state["window"] += 1
            if feed.match_status_at(end_min) == "finished":
                team2, opp2 = aggregate(score_codes)
                app.set_screen(FinalScreen(app, team2, opp2, None))
            else:
                _run_window(app, feed, pool, session, state, score_codes)

        app.set_screen(RevealScreen(app, lines, cont))

    app.set_screen(PredictScreen(app, available, after_predict))
```

- [ ] **Step 2: Update `src/main.py`**

```python
# src/main.py
"""Desktop entry point."""
import asyncio
from src.ui.app import App
from src.ui import demo_flow


async def main() -> None:
    app = App()
    demo_flow.start(app)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Update `main.py` (web entry) to import the same flow**

Read the existing `main.py` first; ensure it ends up calling `asyncio.run(main())` from
`src/main.py` semantics. Minimal version:

```python
# main.py  (pygbag web entry)
import asyncio
from src.ui.app import App
from src.ui import demo_flow


async def main() -> None:
    app = App()
    demo_flow.start(app)
    await app.run()


asyncio.run(main())
```

- [ ] **Step 4: Launch and play the demo on desktop**

Run: `.venv/Scripts/python -m src.main`
Expected: window opens; you can draft 6, lock, predict each window, see reveals, reach Full Time. No crash.

- [ ] **Step 5: Run the whole test suite**

Run: `.venv/Scripts/pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/main.py main.py src/ui/demo_flow.py
git commit -m "feat: playable single-device demo flow with mock feed"
```

---

## Phase 6: Web Build & Verification

### Task 6.1: pygbag mobile build

**Files:**
- Reference: `TOOLS/build_web_mobile.py`, `WEB_BUILD/index_mobile.html`

- [ ] **Step 1: Read the existing mobile build tooling**

Read `TOOLS/build_web_mobile.py` and `WEB_BUILD/web_build_notes.md` to follow the
established build path before changing anything.

- [ ] **Step 2: Run the mobile build**

Run: `.venv/Scripts/python TOOLS/build_web_mobile.py`
(or, if that wraps pygbag) `.venv/Scripts/python -m pygbag --build .`
Expected: `build/web/` is produced with no errors.

- [ ] **Step 3: Serve and smoke-test in a browser (portrait)**

Run: `.venv/Scripts/python -m pygbag .`
Open the served URL in a mobile-emulated browser viewport. Confirm the draft screen renders
in portrait and is tappable.

- [ ] **Step 4: Append to log.md and commit**

Append: `YYYY-MM-DD | pygbag mobile build OK; demo flow playable in browser | TOOLS/build_web_mobile.py`

```bash
git add log.md
git commit -m "chore: verify pygbag mobile build of demo flow"
```

---

### Task 6.2: Final full-suite verification

- [ ] **Step 1: Run the complete test suite**

Run: `.venv/Scripts/pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Confirm the engine has zero pygame imports**

Run: `grep -rl "import pygame" src/game/ || echo "OK no pygame in src/game"`
Expected: prints `OK no pygame in src/game`.

- [ ] **Step 3: Confirm the game still launches**

Run: `.venv/Scripts/python -m src.main`
Expected: launches and is playable.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: full verification of coop soccer v1 vertical slice"
```

---

## Deferred to a follow-up plan (NOT in this plan)

- Real multi-device flow: join screen (session code + seed exchange), POSTing drafts/picks
  to the relay, polling the opponent's picks and score events, and reconciling two
  `GameSession`s into the shared score. (The relay + clients are built here; wiring the live
  two-player loop into the UI is the next plan.)
- Wiring the live `feed_cache.php` -> `FeedClient` -> `normalize_soccer` path into the
  watch loop (only after Task 3.1 confirms the data source).
- Opponent-mode UI (virtual vs real home/away) and the real-scoreline comparison at full time.
- Audio, art polish, error states (no match today, API down, relay unreachable, opponent
  pick timeout).
- NHL feed adapter (engine is already generic; only a new adapter is needed).
```
