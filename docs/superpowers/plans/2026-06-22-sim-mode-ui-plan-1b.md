# Sim-Mode Dungeon UI Implementation Plan (Plan 1b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dungeon crawl playable end-to-end in SIM mode on a single device against a recorded World Cup match: buy gear in a shop, predict five stats per 15-minute window, watch the party crawl the depth track through monster gates, and finish on a "% dungeon completed" screen.

**Architecture:** The pure dungeon engine (Plan 1a) is done. This plan adds (1) ONE new pure module `src/game/crawl.py` (`CrawlSession`) that sequences both halves — shared treasury, per-fighter loadouts, the live `DungeonState`, and the crawl log — taking per-window actuals as input so it stays fully unit-testable; and (2) a thin pygame UI layer (shop screen, dungeon play screen, dungeon final screen, depth-meter widget, icon loader/generator) plus a `DungeonSimFlow` that wires Splash -> Pregame -> Shop(H1) -> 3 windows -> Shop(H2) -> 3 windows -> Final. The live/relay path (`live_play_screen.py`) is untouched; that is Plan 2.

**Tech Stack:** Python 3.11, pygame-ce, pygbag (portrait 414x896). Venv only (`.venv/Scripts/python`). Deterministic `random.Random(seed=99)`. ASCII-only in all print/log/`.md` output (pygame surface strings may be unicode). No magic numbers (all geometry in `config/layout_config.json`, all rules in `config/game_config.json`). `src/game/` keeps ZERO pygame imports.

---

## How verification works in this plan

The golden rule forbids pygame in `tests/`, so the two big pygame screens cannot be pytest-covered. Verification is layered:

- **Pure logic** (`src/game/crawl.py`): full `pytest` coverage (TDD).
- **UI screens / widgets / loaders**: verified by (a) the headless integration smoke `TOOLS/smoke_dungeon.py` (Task 10), which constructs every new screen with an SDL dummy display and calls `.draw()` plus drives a full two-half `CrawlSession`, and (b) a desktop launch check `.venv/Scripts/python src/main.py --dungeon`.

All test/pytest commands run as `.venv/Scripts/python -m pytest`. NEVER bare `python`.

---

## File Structure

**Create:**
- `src/game/crawl.py` — pure `CrawlSession`: treasury + loadouts + `DungeonState` + log across both halves. Zero pygame.
- `tests/test_crawl.py` — unit tests for `CrawlSession`.
- `src/utils/asset_loader.py` — lazy, cached PNG icon loader; returns `None` when a file is absent (callers fall back to a drawn shape).
- `TOOLS/make_icons.py` — offline generator that renders the nine 64x64 icon PNGs with pygame primitives (no hand art).
- `src/ui/screens/shop_screen.py` — `ShopScreen`: buy/sell items, shared treasury, loadout strip, "Descend" button.
- `src/ui/screens/dungeon_play_screen.py` — `DungeonPlayScreen`: five stat dials, depth meter, Power/wounds/treasury, crawl log, window-color cells; resolves one window and shows the outcome.
- `TOOLS/smoke_dungeon.py` — headless integration smoke driving a full two-half crawl + constructing every new screen.

**Modify:**
- `config/game_config.json` — add `game.dungeon_party_size`, `assets.icon_subdir`, `launcher.dungeon_label`.
- `config/layout_config.json` — add all new UI geometry keys (shop, dungeon play, depth meter).
- `src/ui/widgets.py` — add `draw_depth_meter(...)` helper.
- `src/ui/screens/status_screens.py` — add `DungeonFinalScreen`.
- `src/ui/flow.py` — add `DungeonSimFlow` + `start_dungeon_sim(...)` + a per-window actuals helper.
- `src/main.py` — add `--dungeon` entry.
- `src/ui/screens/launcher_screen.py` — no change needed (it already renders any `(label, action)` list); `flow.start_launcher` adds a third option.
- `log.md` — session entry.

---

### Task 1: Config additions (no code, just constants)

**Files:**
- Modify: `config/game_config.json`
- Modify: `config/layout_config.json`

- [ ] **Step 1: Add three keys to `config/game_config.json`**

In the `"game"` block, add after `"loadout_size": 6,`:

```json
    "dungeon_party_size": 1,
```

In the `"launcher"` block, add after `"sim_label": "Test game (simulated)",`:

```json
    "dungeon_label": "Dungeon crawl (simulated)",
```

In the `"assets"` block, add after `"image_dir": "assets/images",`:

```json
    "icon_subdir": "icons",
```

- [ ] **Step 2: Add new UI geometry to `config/layout_config.json`**

Insert these keys before the final closing `}` (keep valid JSON — add a comma after the current last entry `"fixsel_card_title_max": 26`):

```json
  "shop_list_top": 116,
  "shop_row_h": 64,
  "shop_row_gap": 8,
  "shop_icon": 44,
  "shop_name_size": 20,
  "shop_sub_size": 15,
  "shop_done_btn_h": 56,
  "shop_header_size": 22,
  "shop_gold_size": 18,
  "shop_hint_size": 15,
  "shop_loadout_label_size": 15,

  "dp;_header_size": 18,
  "dp_header_y": 14,
  "dp_score_size": 15,
  "dp_score_y": 38,
  "dp_status_size": 16,
  "dp_status_y": 60,
  "dp_content_top": 92,
  "dp_stat_row_h": 48,
  "dp_stat_gap": 6,
  "dp_stat_size": 19,
  "dp_section_size": 16,
  "dp_section_gap": 24,
  "dp_log_h": 150,
  "dp_log_label_size": 15,
  "dp_cells_h": 28,
  "dp_cell_gap": 6,
  "dp_btn_h": 56,
  "dp_hint_size": 15,

  "depth_meter_h": 26,
  "depth_pip_gap": 3,
  "depth_label_size": 14,

  "dfinal_title_size": 40,
  "dfinal_pct_size": 56,
  "dfinal_sub_size": 20,
  "dfinal_hint_size": 16
```

NOTE: the key `"dp;_header_size"` above is a typo — write it as `"dp_header_size": 18,` (the screen in Task 7 reads `dp_header_size`). Use `dp_header_size`.

- [ ] **Step 3: Verify JSON is valid and the suite still loads config**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (263 passed, same as Plan 1a — config still parses, no behavior change).

Run: `.venv/Scripts/python -c "from src.utils.constants import CONFIG, LAYOUT; print(CONFIG['game']['dungeon_party_size'], CONFIG['assets']['icon_subdir'], LAYOUT.i('shop_row_h'), LAYOUT.i('dp_header_size'))"`
Expected output: `1 icons 64 18`

- [ ] **Step 4: Commit**

```bash
git add config/game_config.json config/layout_config.json
git commit -m "feat(config): add dungeon party size, icon subdir, and sim-UI geometry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `CrawlSession` — pure two-half orchestration

**Files:**
- Create: `src/game/crawl.py`
- Test: `tests/test_crawl.py`

`CrawlSession` owns everything the UI must not: the shared treasury, one `Loadout` per fighter, the live `DungeonState`, the running crawl log, and the per-window color history. The UI passes in per-window `actuals` (extracted from the feed) so this module never imports pygame or touches the feed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_crawl.py`:

```python
# tests/test_crawl.py
import random

import pytest

from src.game.athlete import DraftedAthlete
from src.game.crawl import CrawlSession
from src.game.treasury import base_treasury


def _pool():
    rows = [("sccr-1", "L. Messi", "Attacker"),    # -> weapon
            ("sccr-2", "V. van Dijk", "Defender"),  # -> armor
            ("sccr-3", "L. Modric", "Midfielder"),  # -> consumable
            ("sccr-4", "T. Courtois", "Goalkeeper")]  # -> magic
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="World", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _session(party_size=1):
    return CrawlSession(party_size=party_size, pool=_pool(), rng=random.Random(99))


def test_starts_with_base_treasury_and_one_loadout_per_fighter():
    s = _session(party_size=2)
    assert s.treasury == base_treasury(2)
    assert len(s.loadouts) == 2
    assert s.half == 1
    assert s.state.half == 1


def test_catalog_has_one_item_per_athlete_with_all_categories():
    s = _session()
    cats = {it.category for it in s.catalog()}
    assert cats == {"weapon", "armor", "consumable", "magic"}


def test_buy_deducts_gold_and_adds_to_loadout():
    s = _session()
    weapon = next(it for it in s.catalog() if it.category == "weapon")
    before = s.treasury
    ok, reason = s.buy(0, weapon)
    assert ok and reason == ""
    assert s.treasury == before - weapon.price
    assert s.loadouts[0].has_weapon()


def test_buy_refused_when_too_expensive():
    s = _session()
    s.treasury = 10
    weapon = next(it for it in s.catalog() if it.category == "weapon")
    ok, reason = s.buy(0, weapon)
    assert not ok and reason == "not enough gold"
    assert s.treasury == 10


def test_sell_refunds_full_price_and_removes_item():
    s = _session()
    armor = next(it for it in s.catalog() if it.category == "armor")
    s.buy(0, armor)
    mid = s.treasury
    s.sell(0, armor.item_id)
    assert s.treasury == mid + armor.price
    assert not any(it.item_id == armor.item_id for it in s.loadouts[0].items)


def test_resolve_window_advances_depth_logs_and_banks_gold():
    s = _session()
    lines = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}
    actuals = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}  # all EXACT
    before_gold = s.treasury
    result = s.resolve_window([lines], actuals, "H1 W1")
    assert s.state.depth > 0
    assert s.window_index == 1
    assert s.window_colors == [result.color]
    assert s.treasury >= before_gold  # tiles earn gold
    assert any("H1 W1" in line for line in s.log)


def test_consumables_are_dropped_after_each_window():
    s = _session()
    cons = next(it for it in s.catalog() if it.category == "consumable")
    s.buy(0, cons)
    assert any(it.category == "consumable" for it in s.loadouts[0].items)
    s.resolve_window([{"goal": 0, "shot": 0, "corner": 0, "card": 0, "foul": 0}], {}, "H1 W1")
    assert not any(it.category == "consumable" for it in s.loadouts[0].items)


def test_begin_second_half_carries_power_resets_depth_and_window():
    s = _session()
    s.state.depth = 9
    s.state.power = 4
    s.window_index = 3
    s.begin_second_half()
    assert s.half == 2
    assert s.state.half == 2
    assert s.state.depth == 0
    assert s.state.power == 4          # Power persists across halves
    assert s.window_index == 0
    assert s.cleared_prev_halves == 9  # half-1 depth banked for the score


def test_percent_and_score_label_span_both_halves():
    s = _session()
    s.state.depth = 12        # full half-1 (12 tiles for party of 1)
    s.begin_second_half()
    s.state.depth = 8         # half of half-2 (16 tiles)
    assert s.cleared_total() == 20
    assert 0 < s.percent() < 100
    assert s.score_label().startswith("Depth 20/28")


def test_match_over_only_after_second_half_windows():
    s = _session()
    s.window_index = 3
    assert s.half_over() and not s.match_over()   # half 1 just ended
    s.begin_second_half()
    s.window_index = 3
    assert s.match_over()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_crawl.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.game.crawl'`.

- [ ] **Step 3: Write `src/game/crawl.py`**

```python
# src/game/crawl.py
"""Pure orchestration of one cooperative dungeon crawl across both halves: a shared party
treasury, one loadout per fighter, the live DungeonState, and the running crawl log. The UI
feeds in per-window actuals; this module owns all economy / loadout / resolution sequencing
so it stays fully testable. rng is injected (random.Random). Zero pygame, zero feed access."""
import random
from dataclasses import dataclass, field

from src.game.dungeon import DungeonState
from src.game.items import Item, build_catalog
from src.game.loadout import Loadout
from src.game.score import percent_complete, total_tiles_game
from src.game.treasury import base_treasury, second_half_multiplier
from src.game.window_resolver import PartyGear, WindowResult, resolve_window
from src.utils.constants import CONFIG

_WINDOWS_PER_HALF = int(CONFIG["game"]["windows_per_half"])


@dataclass
class CrawlSession:
    party_size: int
    pool: list                       # list[DraftedAthlete] from the match lineup
    rng: random.Random
    half: int = 1
    treasury: int = 0
    window_index: int = 0            # windows resolved in the current half
    cleared_prev_halves: int = 0     # tiles cleared in finished halves (for the score)
    loadouts: list = field(default_factory=list)        # list[Loadout], one per fighter
    log: list = field(default_factory=list)             # crawl-log lines, oldest first
    window_colors: list = field(default_factory=list)   # one color per resolved window
    state: DungeonState = field(init=False)

    def __post_init__(self) -> None:
        if not self.loadouts:
            self.loadouts = [Loadout() for _ in range(self.party_size)]
        if not self.treasury:
            self.treasury = base_treasury(self.party_size)
        self.state = DungeonState(half=self.half, party_size=self.party_size)

    # -- shop --
    def price_multiplier(self) -> float:
        return second_half_multiplier() if self.half == 2 else 1.0

    def catalog(self) -> list:
        return build_catalog(self.pool, self.half, self.price_multiplier())

    def buy(self, member: int, item: Item) -> tuple[bool, str]:
        loadout = self.loadouts[member]
        ok, reason = loadout.can_add(item)
        if not ok:
            return False, reason
        if item.price > self.treasury:
            return False, "not enough gold"
        loadout.add(item)
        self.treasury -= item.price
        return True, ""

    def sell(self, member: int, item_id: str) -> None:
        loadout = self.loadouts[member]
        for it in loadout.items:
            if it.item_id == item_id:
                self.treasury += it.price
                loadout.remove(item_id)
                return

    # -- resolution --
    def party_gear(self) -> PartyGear:
        return PartyGear(
            weapon_bonus=max((l.best_weapon_bonus() for l in self.loadouts), default=0),
            armor_soak=max((l.best_armor_soak() for l in self.loadouts), default=0),
            has_reroll=any(l.has_reroll() for l in self.loadouts),
            consumable_value=sum(it.effect.get("value", 0)
                                 for l in self.loadouts for it in l.items
                                 if it.category == "consumable"))

    def resolve_window(self, fighter_lines: list, actuals: dict,
                       window_label: str) -> WindowResult:
        gear = self.party_gear()
        result = resolve_window(self.rng, self.state, gear, fighter_lines,
                                actuals, window_label)
        self.treasury += result.gold
        self.window_index += 1
        self.window_colors.append(result.color)
        self.log.extend(result.log)
        self._drop_consumables()
        return result

    def _drop_consumables(self) -> None:
        """Consumables persist for one round only; spent or not, they leave after the window."""
        for loadout in self.loadouts:
            for it in list(loadout.items):
                if it.persist == "round":
                    loadout.remove(it.item_id)

    # -- half / score --
    def begin_second_half(self) -> None:
        self.cleared_prev_halves += self.state.depth
        self.half = 2
        self.window_index = 0
        carried_power = self.state.power           # Power is persistent across the game
        self.state = DungeonState(half=2, party_size=self.party_size, power=carried_power)

    def windows_remaining(self) -> int:
        return max(0, _WINDOWS_PER_HALF - self.window_index)

    def half_over(self) -> bool:
        return self.state.finished or self.window_index >= _WINDOWS_PER_HALF

    def match_over(self) -> bool:
        return self.half == 2 and self.half_over()

    def cleared_total(self) -> int:
        return self.cleared_prev_halves + self.state.depth

    def percent(self) -> int:
        return percent_complete(self.cleared_total(), self.party_size)

    def score_label(self) -> str:
        total = total_tiles_game(self.party_size)
        return f"Depth {self.cleared_total()}/{total} ({self.percent()}%)"
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_crawl.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (273 passed).

- [ ] **Step 6: Commit**

```bash
git add src/game/crawl.py tests/test_crawl.py
git commit -m "feat(game): add CrawlSession pure two-half dungeon orchestration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Icon loader (`asset_loader.py`)

**Files:**
- Create: `src/utils/asset_loader.py`

Lazy, cached loader. Returns `None` when the PNG is missing so every caller can fall back to a drawn primitive — the web build never crashes on a missing asset. Lives in `src/utils/` (not `src/game/`) because it imports pygame.

- [ ] **Step 1: Write `src/utils/asset_loader.py`**

```python
# src/utils/asset_loader.py
"""Lazy, cached image loading for the UI. Returns None when a file is absent so callers
fall back to a drawn primitive (keeps the web build alive if an icon is missing).

Icons live at <repo>/assets/images/icons/<name>.png (config assets.image_dir / icon_subdir).
Names used by the dungeon UI: weapon, armor, consumable, magic, tile, gate, monster,
power, wound."""
from pathlib import Path
from typing import Optional

import pygame

from src.utils.constants import CONFIG

_ROOT = Path(__file__).resolve().parents[2]
_ICON_DIR = _ROOT / CONFIG["assets"]["image_dir"] / CONFIG["assets"]["icon_subdir"]
_CACHE: dict[str, Optional[pygame.Surface]] = {}


def load_icon(name: str) -> Optional[pygame.Surface]:
    """Return the cached icon Surface for `name`, or None if the file is missing/unloadable."""
    if name in _CACHE:
        return _CACHE[name]
    path = _ICON_DIR / f"{name}.png"
    surf: Optional[pygame.Surface] = None
    if path.exists():
        try:
            loaded = pygame.image.load(str(path))
            try:
                surf = loaded.convert_alpha()   # fast blits once a display exists
            except pygame.error:
                surf = loaded                    # no display yet -- use the raw surface
        except pygame.error:
            surf = None
    _CACHE[name] = surf
    return surf
```

- [ ] **Step 2: Verify it imports (no display, returns None for a missing icon)**

Run: `.venv/Scripts/python -c "import os; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; pygame.init(); from src.utils.asset_loader import load_icon; print(load_icon('nope') is None)"`
Expected output: `True`

- [ ] **Step 3: Commit**

```bash
git add src/utils/asset_loader.py
git commit -m "feat(utils): add cached icon loader with missing-file fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Icon generator (`TOOLS/make_icons.py`)

**Files:**
- Create: `TOOLS/make_icons.py`

Renders nine 64x64 PNGs with pygame primitives (no hand-drawn art) into `assets/images/icons/`. Deterministic. Run once now; re-runnable any time.

- [ ] **Step 1: Write `TOOLS/make_icons.py`**

```python
# TOOLS/make_icons.py
"""Generate the dungeon icon set as simple 64x64 PNGs using pygame primitives.

Run:  .venv/Scripts/python TOOLS/make_icons.py
Writes:  assets/images/icons/{weapon,armor,consumable,magic,tile,gate,monster,power,wound}.png

ASCII-only output. Headless (SDL dummy driver) so it needs no display."""
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from src.utils.constants import CONFIG  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / CONFIG["assets"]["image_dir"] / CONFIG["assets"]["icon_subdir"]
_C = CONFIG["colors"]
_SIZE = 64
_PAD = 8


def _surf() -> pygame.Surface:
    return pygame.Surface((_SIZE, _SIZE), pygame.SRCALPHA)


def _weapon() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["red"], [(32, 6), (40, 44), (24, 44)])      # blade
    pygame.draw.rect(s, _C["white"], (28, 44, 8, 14))                      # grip
    pygame.draw.rect(s, _C["white"], (20, 42, 24, 4))                      # cross-guard
    return s


def _armor() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["green"],
                        [(12, 12), (52, 12), (52, 36), (32, 56), (12, 36)])
    pygame.draw.polygon(s, _C["white"],
                        [(12, 12), (52, 12), (52, 36), (32, 56), (12, 36)], 3)
    return s


def _consumable() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["white"], (28, 8, 8, 10))                       # neck
    pygame.draw.circle(s, _C["orange"], (32, 40), 18)                      # flask
    pygame.draw.circle(s, _C["white"], (32, 40), 18, 3)
    return s


def _magic() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["accent"], [(32, 8), (56, 32), (32, 56), (8, 32)])
    pygame.draw.polygon(s, _C["white"], [(32, 8), (56, 32), (32, 56), (8, 32)], 3)
    return s


def _tile() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["border"], (_PAD, _PAD, _SIZE - 2 * _PAD, _SIZE - 2 * _PAD),
                     border_radius=6)
    return s


def _gate() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["gold"], (12, 20, 40, 38))
    pygame.draw.circle(s, _C["gold"], (32, 20), 20)
    pygame.draw.rect(s, _C["background"], (24, 30, 16, 28))               # archway
    pygame.draw.circle(s, _C["background"], (32, 30), 8)
    return s


def _monster() -> pygame.Surface:
    s = _surf()
    pygame.draw.circle(s, _C["red"], (32, 34), 22)
    pygame.draw.circle(s, _C["white"], (24, 30), 5)
    pygame.draw.circle(s, _C["white"], (40, 30), 5)
    pygame.draw.circle(s, _C["background"], (24, 30), 2)
    pygame.draw.circle(s, _C["background"], (40, 30), 2)
    return s


def _power() -> pygame.Surface:
    s = _surf()
    pts = [(32, 6), (39, 26), (60, 26), (43, 39), (49, 59),
           (32, 47), (15, 59), (21, 39), (4, 26), (25, 26)]
    pygame.draw.polygon(s, _C["gold"], pts)
    return s


def _wound() -> pygame.Surface:
    s = _surf()
    pygame.draw.line(s, _C["red"], (14, 14), (50, 50), 8)
    pygame.draw.line(s, _C["red"], (50, 14), (14, 50), 8)
    return s


_ICONS = {
    "weapon": _weapon, "armor": _armor, "consumable": _consumable, "magic": _magic,
    "tile": _tile, "gate": _gate, "monster": _monster, "power": _power, "wound": _wound,
}


def main() -> None:
    pygame.init()
    _OUT.mkdir(parents=True, exist_ok=True)
    for name, builder in _ICONS.items():
        path = _OUT / f"{name}.png"
        pygame.image.save(builder(), str(path))
        print(f"OK wrote {path}")
    print(f"OK {len(_ICONS)} icons written to {_OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

Run: `.venv/Scripts/python TOOLS/make_icons.py`
Expected: nine `OK wrote ...` lines then `OK 9 icons written to ...assets/images/icons`.

- [ ] **Step 3: Verify the files exist**

Run: `.venv/Scripts/python -c "from pathlib import Path; from src.utils.constants import CONFIG; d=Path(CONFIG['assets']['image_dir'])/CONFIG['assets']['icon_subdir']; print(sorted(p.name for p in d.glob('*.png')))"`
Expected: `['armor.png', 'consumable.png', 'gate.png', 'magic.png', 'monster.png', 'power.png', 'tile.png', 'weapon.png', 'wound.png']`

- [ ] **Step 4: Commit (tool + generated PNGs)**

```bash
git add TOOLS/make_icons.py assets/images/icons
git commit -m "feat(tools): add icon generator and generated dungeon icon set

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Depth-meter widget

**Files:**
- Modify: `src/ui/widgets.py`

A horizontal pip track: one cell per tile, gate cells outlined in gold, cleared cells filled in the window color, the rest dim. A `depth/total` caption sits above. Geometry from `layout_config` (`depth_meter_h`, `depth_pip_gap`, `depth_label_size`).

- [ ] **Step 1: Add `draw_depth_meter` to `src/ui/widgets.py`**

Append at the end of `src/ui/widgets.py`:

```python
def draw_depth_meter(surface: pygame.Surface, rect: pygame.Rect, depth: int,
                     total: int, gate_step: int, color_key: str) -> None:
    """A pip track of `total` cells inside `rect`. Cells 0..depth-1 fill in colors[color_key];
    the rest are dim. Every `gate_step`-th boundary cell is outlined in gold. A 'depth/total'
    caption renders just above the track."""
    cap_h = LAYOUT.i("depth_label_size", 14) + 4
    lf = font(LAYOUT.i("depth_label_size", 14))
    surface.blit(lf.render(f"Depth {depth}/{total}", True, _C["text_dim"]),
                 (rect.x, rect.y))
    track = pygame.Rect(rect.x, rect.y + cap_h, rect.width,
                        LAYOUT.i("depth_meter_h", 26))
    gap = LAYOUT.i("depth_pip_gap", 3)
    n = max(1, total)
    cell_w = max(2, (track.width - (n - 1) * gap) // n)
    fill = _C.get(color_key, _C["orange"])
    for i in range(n):
        x = track.x + i * (cell_w + gap)
        cell = pygame.Rect(x, track.y, cell_w, track.height)
        is_gate = gate_step > 0 and (i + 1) % gate_step == 0
        pygame.draw.rect(surface, fill if i < depth else _C["surface"], cell,
                         border_radius=3)
        if is_gate:
            pygame.draw.rect(surface, _C["gold"], cell, width=2, border_radius=3)
```

- [ ] **Step 2: Verify it imports and runs headless**

Run: `.venv/Scripts/python -c "import os; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; pygame.init(); s=pygame.display.set_mode((414,896)); from src.ui.widgets import draw_depth_meter; draw_depth_meter(s, pygame.Rect(20,400,374,40), 5, 12, 8, 'green'); print('OK')"`
Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ui/widgets.py
git commit -m "feat(ui): add draw_depth_meter pip-track widget

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Shop screen

**Files:**
- Create: `src/ui/screens/shop_screen.py`

Scrollable list of catalog items (icon + name + category + price), a pinned header showing the half and the shared treasury, and a "Descend" button. Tap an item row to buy it (errors shown inline on slot/affordability/one-two-handed rules). Owned items render with an "OWNED — tap to sell" marker; tapping them sells back at full price. SIM 'R' auto-buys the first affordable weapon then armor and descends. Modeled on `draft_screen.py`'s viewport + `ScrollButtons` + bottom-button pattern.

- [ ] **Step 1: Write `src/ui/screens/shop_screen.py`**

```python
# src/ui/screens/shop_screen.py
"""Dungeon shop: spend the shared party treasury on items generated from the live lineup.

Tap an unowned row to buy it (subject to slot / affordability / one-two-handed rules; the
reason shows inline on refusal). Tap an owned row to sell it back at full price. 'Descend'
enters the dungeon. SIM 'R' auto-buys the first affordable weapon + armor, then descends.

For SIM (single device) the whole party shares one loadout slot index (`member`), default 0.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, ScrollButtons, font
from src.ui.sim import SimMode
from src.game.crawl import CrawlSession
from src.utils.asset_loader import load_icon
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_HALF_LABEL = CONFIG["game"]["half_label"]
_SECOND_HALF_LABEL = CONFIG["game"]["second_half_label"]


class ShopScreen(Screen):
    def __init__(self, app: "App", session: CrawlSession,
                 on_done: Callable[[], None], sim: Optional[SimMode] = None,
                 member: int = 0) -> None:
        super().__init__(app)
        self.session = session
        self.on_done = on_done
        self.sim = sim
        self.member = member
        self.catalog = session.catalog()
        self.feedback = ""
        self.scroll = 0
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.done_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("shop_done_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("shop_done_btn_h", 56)),
            "Descend into the dungeon")
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- geometry --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("shop_list_top", 116)
        bottom = self.done_btn.rect.top - 8
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _row_step(self) -> int:
        return LAYOUT.i("shop_row_h", 64) + LAYOUT.i("shop_row_gap", 8)

    def _max_scroll(self) -> int:
        return max(0, len(self.catalog) * self._row_step() - self._viewport().height)

    def _row_rect(self, i: int) -> pygame.Rect:
        vp = self._viewport()
        w = vp.width - ScrollButtons.gutter()
        return pygame.Rect(vp.x, vp.top + i * self._row_step() - self.scroll,
                           w, LAYOUT.i("shop_row_h", 64))

    def _owned(self, item) -> bool:
        return any(it.item_id == item.item_id for it in self.session.loadouts[self.member].items)

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_r):
            self._auto_buy()
            self.on_done()
            return
        if event.type == pygame.MOUSEWHEEL:
            if self._viewport().collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll, self._max_scroll())
            return
        if self.done_btn.hit(event.pos):
            self.on_done()
            return
        if not self._viewport().collidepoint(event.pos):
            return
        for i, item in enumerate(self.catalog):
            if self._row_rect(i).collidepoint(event.pos):
                self._tap_item(item)
                return

    def _tap_item(self, item) -> None:
        if self._owned(item):
            self.session.sell(self.member, item.item_id)
            self.feedback = f"Sold {item.name} (+{item.price}g)"
        else:
            ok, reason = self.session.buy(self.member, item)
            self.feedback = (f"Bought {item.name} (-{item.price}g)" if ok
                             else f"Cannot buy {item.name}: {reason}")

    def _auto_buy(self) -> None:
        for category in ("weapon", "armor"):
            for item in self.catalog:
                if item.category == category and self.session.buy(self.member, item)[0]:
                    break

    def update(self, dt: float) -> None:
        ...

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        half_label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        hf = font(LAYOUT.i("shop_header_size", 22))
        surface.blit(hf.render(f"Shop -- {half_label}", True, _C["white"]), (m, 16))
        gf = font(LAYOUT.i("shop_gold_size", 18))
        loadout = self.session.loadouts[self.member]
        surface.blit(gf.render(
            f"Gold {self.session.treasury}   Slots {len(loadout.items)}/{loadout.slot_cap()}",
            True, _C["gold"]), (m, 48))
        if self.feedback:
            ff = font(LAYOUT.i("shop_hint_size", 15))
            surface.blit(ff.render(self.feedback[:46], True, _C["accent"]), (m, 78))

        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        nf = font(LAYOUT.i("shop_name_size", 20))
        sf = font(LAYOUT.i("shop_sub_size", 15))
        for i, item in enumerate(self.catalog):
            r = self._row_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            self._draw_row(surface, r, item, nf, sf)
        surface.set_clip(prev)

        if self._max_scroll() > 0:
            self.scroll_btns.draw(surface, self.scroll, self._max_scroll())
        self.done_btn.draw(surface, nf)

    def _draw_row(self, surface: pygame.Surface, r: pygame.Rect, item,
                  nf: pygame.font.Font, sf: pygame.font.Font) -> None:
        owned = self._owned(item)
        bg = _C["accent"] if owned else _C["surface"]
        pygame.draw.rect(surface, bg, r, border_radius=8)
        pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
        size = LAYOUT.i("shop_icon", 44)
        icon = load_icon(item.category)
        icon_box = pygame.Rect(r.x + 8, r.centery - size // 2, size, size)
        if icon is not None:
            surface.blit(pygame.transform.smoothscale(icon, (size, size)), icon_box)
        else:
            pygame.draw.rect(surface, _C["border"], icon_box, border_radius=6)
        tx = icon_box.right + 10
        surface.blit(nf.render(item.name[:18], True, _C["white"]), (tx, r.y + 8))
        sub = f"{item.category}  {'*' * item.stars}  {item.price}g"
        surface.blit(sf.render(sub, True, _C["text_dim"]), (tx, r.y + 36))
        tag = "OWNED -- tap to sell" if owned else "tap to buy"
        ts = sf.render(tag, True, _C["background"] if owned else _C["accent"])
        surface.blit(ts, (r.right - ts.get_width() - 10, r.y + 8))
```

- [ ] **Step 2: Verify it constructs and draws headless**

Run:
```bash
.venv/Scripts/python -c "import os, random; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; from src.ui.app import App; from src.game.crawl import CrawlSession; from src.game.replay_feed import ReplayFeed; from src.ui.flow import _pool_from_feed; from src.ui.screens.shop_screen import ShopScreen; from src.ui.sim import SimMode; app=App(); f=ReplayFeed.from_file('assets/data/simulations/wc2018_final_fra_cro.json'); s=CrawlSession(party_size=1, pool=_pool_from_feed(f), rng=random.Random(99)); sc=ShopScreen(app, s, lambda: None, SimMode(True)); sc.draw(app.screen); print('OK', len(sc.catalog), 'items')"
```
Expected: `OK <N> items` (N = number of starters in the sim lineup), no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/ui/screens/shop_screen.py
git commit -m "feat(ui): add dungeon shop screen (buy/sell, treasury, icons)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Dungeon play screen

**Files:**
- Create: `src/ui/screens/dungeon_play_screen.py`

One window of play. Two phases on one screen:
- **predict** — five stat dials (goal/shot/corner/card/foul) each with -/+ steppers; a "Descend" button calls `on_descend(lines)` (the flow resolves the window and returns a `WindowResult`).
- **resolved** — the just-resolved outcome: the depth meter advances, window-color cells fill, Power/wounds/treasury update, the crawl log shows the new lines; a "Continue" button calls `on_continue()`.

Header shows the window label, the real match line (teams + goals so far + minute) from the feed, and the party score (`Depth d/total (p%)`). SIM 'A' auto-fills the default lines; 'F' auto-fills and descends.

NOTE on the scoreline: the recorded sim snapshots carry only an aggregate `goals` count (no per-team split), so the header shows total goals + minute, e.g. `France v Croatia  goals 3 (45')`. This is the honest data available offline; the live path (Plan 2) will show the true per-team scoreline.

- [ ] **Step 1: Write `src/ui/screens/dungeon_play_screen.py`**

```python
# src/ui/screens/dungeon_play_screen.py
"""One 15-minute window of the dungeon crawl, single device.

Phase 'predict': five stat dials with -/+ steppers and a Descend button -> on_descend(lines)
returns the resolved WindowResult. Phase 'resolved': the advanced depth meter, window-color
cells, Power / wounds / treasury, and the crawl log; a Continue button -> on_continue().

lines is a dict {goal, shot, corner, card, foul} of predicted lines for the (single-device)
party. SIM 'A' auto-fills defaults; 'F' auto-fills and descends."""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, LogList, draw_depth_meter, font
from src.ui.sim import SimMode
from src.game.crawl import CrawlSession
from src.game.dungeon import gate_step
from src.game.window_resolver import WindowResult
from src.utils.asset_loader import load_icon
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_HALF_MIN = CONFIG["game"]["half_minutes"]


class DungeonPlayScreen(Screen):
    def __init__(self, app: "App", session: CrawlSession, feed,
                 window: int, label: str,
                 on_descend: Callable[[dict], WindowResult],
                 on_continue: Callable[[], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.session = session
        self.feed = feed
        self.window = window
        self.label = label
        self.on_descend = on_descend
        self.on_continue = on_continue
        self.sim = sim
        self.phase = "predict"
        self.result: Optional[WindowResult] = None
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.log = LogList(pygame.Rect(m, LAYOUT.i("dp_content_top", 92),
                                       sw - 2 * m, LAYOUT.i("dp_log_h", 150)))
        for line in session.log:
            self.log.add(line)
        self.action_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dp_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("dp_btn_h", 56)),
            "Descend")

    # -- geometry for the predict-phase stat rows --
    def _stat_step(self) -> int:
        return LAYOUT.i("dp_stat_row_h", 48) + LAYOUT.i("dp_stat_gap", 6)

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("dp_content_top", 92)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * self._stat_step(), w, LAYOUT.i("dp_stat_row_h", 48))

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.phase == "predict":
            if self.sim and self.sim.is_key(event, pygame.K_a):
                return  # defaults already set; nothing to change
            if self.sim and self.sim.is_key(event, pygame.K_f):
                self._descend()
                return
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
            if self.action_btn.hit(event.pos):
                self._descend()
                return
            for i, s in enumerate(_STATS):
                r = self._stat_rect(i)
                if r.collidepoint(event.pos):
                    self._tap_stat(s["code"], event.pos[0], r)
                    return
        else:  # resolved
            self.log.handle(event)
            if self.sim and self.sim.is_key(event, pygame.K_s):
                self.on_continue()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and self.action_btn.hit(event.pos):
                self.on_continue()

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:
            self.lines[code] += 1
        elif x > r.right - 112:
            self.lines[code] = max(0, self.lines[code] - 1)

    def _descend(self) -> None:
        self.result = self.on_descend(dict(self.lines))
        for line in self.result.log:
            self.log.add(line)
        self.phase = "resolved"
        self.action_btn.label = ("Continue" if not self.session.match_over()
                                 else "See results")

    def update(self, dt: float) -> None:
        ...

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        hf = font(LAYOUT.i("dp_header_size", 18))
        surface.blit(hf.render(self.label, True, _C["accent"]), (m, LAYOUT.i("dp_header_y", 14)))
        sf = font(LAYOUT.i("dp_score_size", 15))
        surface.blit(sf.render(self._match_line(), True, _C["text_dim"]),
                     (m, LAYOUT.i("dp_score_y", 38)))
        stf = font(LAYOUT.i("dp_status_size", 16))
        surface.blit(stf.render(self._status_line(), True, _C["white"]),
                     (m, LAYOUT.i("dp_status_y", 60)))
        if self.phase == "predict":
            self._draw_predict(surface)
        else:
            self._draw_resolved(surface)
        self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))

    def _match_line(self) -> str:
        meta = getattr(self.feed, "meta", {})
        home = meta.get("home_team", "Home")
        away = meta.get("away_team", "Away")
        minute = (self.session.half - 1) * _HALF_MIN + self.window * _WINDOW_MIN
        goals = self.feed.snapshot_at(minute).stats.get("goals", 0)
        return f"{home} v {away}   goals {goals} ({minute}')"

    def _status_line(self) -> str:
        st = self.session.state
        hearts = "<3" * max(0, int(CONFIG["dungeon"]["max_wounds"]) - st.wounds)
        return f"Power {st.power}   Wounds {st.wounds}   Gold {self.session.treasury}   {hearts}"

    def _draw_predict(self, surface: pygame.Surface) -> None:
        sf = font(LAYOUT.i("dp_stat_size", 19))
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            surface.blit(sf.render(f"{s['label']}: {self.lines[s['code']]}", True, _C["white"]),
                         (r.x + 12, r.y + 12))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 10))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 10))

    def _draw_resolved(self, surface: pygame.Surface) -> None:
        self.log.draw(surface)
        m = LAYOUT.i("screen_margin", 20)
        cells_y = self.log.rect.bottom + LAYOUT.i("dp_section_gap", 24)
        self._draw_window_cells(surface, m, cells_y)
        meter_y = cells_y + LAYOUT.i("dp_cells_h", 28) + LAYOUT.i("dp_section_gap", 24)
        draw_depth_meter(
            surface,
            pygame.Rect(m, meter_y, self.app.screen.get_width() - 2 * m, 0),
            self.session.state.depth, self.session.state.total_tiles,
            gate_step(self.session.half), self.result.color if self.result else "orange")

    def _draw_window_cells(self, surface: pygame.Surface, x: int, y: int) -> None:
        h = LAYOUT.i("dp_cells_h", 28)
        gap = LAYOUT.i("dp_cell_gap", 6)
        colors = self.session.window_colors
        for i, key in enumerate(colors):
            cell = pygame.Rect(x + i * (h + gap), y, h, h)
            pygame.draw.rect(surface, _C.get(key, _C["orange"]), cell, border_radius=6)
        icon = load_icon("monster")
        if icon is not None:
            surface.blit(pygame.transform.smoothscale(icon, (h, h)),
                         (self.app.screen.get_width() - x - h, y))
```

- [ ] **Step 2: Verify it constructs and draws both phases headless**

Run:
```bash
.venv/Scripts/python -c "import os, random; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; from src.ui.app import App; from src.game.crawl import CrawlSession; from src.game.replay_feed import ReplayFeed; from src.ui.flow import _pool_from_feed; from src.ui.screens.dungeon_play_screen import DungeonPlayScreen; from src.ui.sim import SimMode; app=App(); f=ReplayFeed.from_file('assets/data/simulations/wc2018_final_fra_cro.json'); s=CrawlSession(party_size=1, pool=_pool_from_feed(f), rng=random.Random(99)); res={'r':None}\nimport src.game.window_resolver as wr\ndef desc(lines):\n    return s.resolve_window([lines], {'goal':1,'shot':2,'corner':3,'card':1,'foul':4}, 'H1 W1')\nsc=DungeonPlayScreen(app, s, f, 1, 'First Half - Window 1/3', desc, lambda: None, SimMode(True)); sc.draw(app.screen); sc._descend(); sc.draw(app.screen); print('OK depth', s.state.depth)"
```
Expected: `OK depth <n>` with n > 0, no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/ui/screens/dungeon_play_screen.py
git commit -m "feat(ui): add dungeon play screen (dials, depth meter, crawl log)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Dungeon final screen

**Files:**
- Modify: `src/ui/screens/status_screens.py`

A dedicated end screen showing the big "% dungeon completed", the depth/total line, and a tap-to-continue. Added alongside the existing screens (does not change `FinalScreen`, which the live path still uses).

- [ ] **Step 1: Append `DungeonFinalScreen` to `src/ui/screens/status_screens.py`**

```python
class DungeonFinalScreen(Screen):
    """End of a dungeon run: the party's percent-completed score, big and centered."""

    def __init__(self, app: "App", percent: int, depth: int, total: int,
                 on_continue: Optional[Callable[..., None]] = None,
                 title: str = "Crawl Complete") -> None:
        super().__init__(app)
        self.percent = percent
        self.depth = depth
        self.total = total
        self.on_continue = on_continue
        self.title = title

    def handle(self, event: pygame.event.Event) -> None:
        if self.on_continue and event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        from src.utils.constants import LAYOUT
        from src.ui.widgets import font
        sw = surface.get_width()
        tf = font(LAYOUT.i("dfinal_title_size", 40))
        t = tf.render(self.title, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, 200)))
        pf = font(LAYOUT.i("dfinal_pct_size", 56))
        p = pf.render(f"{self.percent}%", True, _C["accent"])
        surface.blit(p, p.get_rect(center=(sw // 2, 320)))
        sf = font(LAYOUT.i("dfinal_sub_size", 20))
        s = sf.render(f"dungeon completed -- depth {self.depth} of {self.total}",
                      True, _C["text_dim"])
        surface.blit(s, s.get_rect(center=(sw // 2, 400)))
        if self.on_continue:
            hf = font(LAYOUT.i("dfinal_hint_size", 16))
            h = hf.render("tap to continue", True, _C["text_dim"])
            surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 60)))
```

- [ ] **Step 2: Verify it constructs and draws headless**

Run: `.venv/Scripts/python -c "import os; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; from src.ui.app import App; from src.ui.screens.status_screens import DungeonFinalScreen; app=App(); DungeonFinalScreen(app, 71, 20, 28).draw(app.screen); print('OK')"`
Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ui/screens/status_screens.py
git commit -m "feat(ui): add DungeonFinalScreen showing percent dungeon completed

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `DungeonSimFlow` + entry points

**Files:**
- Modify: `src/ui/flow.py`
- Modify: `src/main.py`

The flow controller for the whole sim crawl, plus the `start_dungeon_sim` entry, a `--dungeon` desktop flag, and a third option on the web launcher.

- [ ] **Step 1: Add imports + `DungeonSimFlow` + entries to `src/ui/flow.py`**

Add to the imports near the other screen imports (after the `from src.ui.screens.status_screens import FinalScreen, RevealScreen` line):

```python
from src.ui.screens.status_screens import DungeonFinalScreen
from src.ui.screens.shop_screen import ShopScreen
from src.ui.screens.dungeon_play_screen import DungeonPlayScreen
from src.game.crawl import CrawlSession
```

Add module-level constants near the other `_...` constants (after `_RNG_SEED = ...`):

```python
_WINDOWS_PER_HALF = CONFIG["game"]["windows_per_half"]
_DUNGEON_PARTY_SIZE = CONFIG["game"]["dungeon_party_size"]
```

Add this class after the `LiveFlow` class (before the `start_live` function):

```python
class DungeonSimFlow:
    """Single-device cooperative dungeon crawl over a recorded match.

    Splash -> Pre-game -> Shop(H1) -> 3 windows -> Shop(H2) -> 3 windows -> Final(% done).
    Deterministic: one fixed RNG seed, no relay, no API. The pure CrawlSession owns all
    economy / loadout / resolution; this flow only sequences screens and extracts the
    per-window actuals from the feed."""

    def __init__(self, app: "App", feed: ReplayFeed, pool: list[DraftedAthlete],
                 sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.sim = sim
        self.app.global_handler = sim.handle_global
        self.app.overlay = sim.draw_overlay
        self.session = CrawlSession(party_size=_DUNGEON_PARTY_SIZE, pool=pool,
                                    rng=random.Random(_RNG_SEED))
        self.window = 1

    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._after_splash, self.sim))

    def _after_splash(self) -> None:
        self.app.set_screen(PregameScreen(self.app, self._fixture(), self._to_shop, self.sim))

    def _fixture(self) -> dict:
        meta = getattr(self.feed, "meta", {})
        label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        return {
            "home": meta.get("home_team", _PREGAME["default_home_team"]),
            "away": meta.get("away_team", _PREGAME["default_away_team"]),
            "competition": meta.get("title", _PREGAME["default_competition"]),
            "label": label,
        }

    def _to_shop(self) -> None:
        self.app.set_screen(ShopScreen(self.app, self.session, self._after_shop, self.sim))

    def _after_shop(self) -> None:
        self.window = 1
        self._play_window()

    def _label(self) -> str:
        half_label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        return f"{half_label} -- Window {self.window}/{_WINDOWS_PER_HALF}"

    def _play_window(self) -> None:
        self.app.set_screen(DungeonPlayScreen(
            self.app, self.session, self.feed, self.window, self._label(),
            self._on_descend, self._on_continue, self.sim))

    def _window_actuals(self) -> dict[str, int]:
        start = (self.session.half - 1) * _HALF_MIN + (self.window - 1) * _WINDOW_MIN
        end = start + _WINDOW_MIN
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _on_descend(self, lines: dict) -> "WindowResult":
        return self.session.resolve_window([lines], self._window_actuals(), self._label())

    def _on_continue(self) -> None:
        if not self.session.half_over():
            self.window += 1
            self._play_window()
        elif self.session.half == 1:
            self.session.begin_second_half()
            self._to_shop()
        else:
            self._to_final()

    def _to_final(self) -> None:
        self.app.set_screen(DungeonFinalScreen(
            self.app, self.session.percent(), self.session.cleared_total(),
            total_tiles_game(self.session.party_size),
            on_continue=None, title=_FULLTIME_LABEL))
```

`_on_descend` references `WindowResult` only in a type hint string; add the import to the top with the other game imports:

```python
from src.game.window_resolver import WindowResult
from src.game.score import total_tiles_game
```

Add the entry function near `start_simulation`:

```python
def start_dungeon_sim(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    DungeonSimFlow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()
```

Add a third option to `start_launcher`'s `options` list (so the web build offers it). Replace the `options = [...]` block in `start_launcher` with:

```python
    def go_dungeon() -> None:
        start_dungeon_sim(app, _LAUNCHER["test_sim"], sim_mode=True)

    options = [
        (_LAUNCHER["live_label"], go_live),
        (_LAUNCHER["sim_label"], go_sim),
        (_LAUNCHER["dungeon_label"], go_dungeon),
    ]
```

- [ ] **Step 2: Add the `--dungeon` desktop flag to `src/main.py`**

In `src/main.py`, add a branch before the `elif "--simdemo" in sys.argv:` line:

```python
    elif "--dungeon" in sys.argv:
        flow.start_dungeon_sim(app, CONFIG["launcher"]["test_sim"], sim_mode=True)
```

Add the needed import at the top of `src/main.py` (after `from src.ui import flow`):

```python
from src.utils.constants import CONFIG
```

Also document it in the module docstring usage block by adding this line after the `--sim` line:

```
  .venv/Scripts/python src/main.py --dungeon            # dungeon crawl on the test sim + SIM
```

- [ ] **Step 3: Verify the suite still passes (pure imports unaffected)**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (273 passed).

- [ ] **Step 4: Verify the dungeon flow constructs headless**

Run:
```bash
.venv/Scripts/python -c "import os; os.environ['SDL_VIDEODRIVER']='dummy'; import pygame; from src.ui.app import App; from src.ui import flow; app=App(); flow.start_dungeon_sim(app, flow.CONFIG['launcher']['test_sim']); print('OK', type(app.current).__name__)"
```
Expected: `OK SplashScreen`

- [ ] **Step 5: Commit**

```bash
git add src/ui/flow.py src/main.py
git commit -m "feat(ui): wire DungeonSimFlow, --dungeon entry, and launcher option

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Headless integration smoke

**Files:**
- Create: `TOOLS/smoke_dungeon.py`

Drives a full two-half crawl against the test sim via `CrawlSession` and the feed actuals (no event loop), AND constructs every new screen with a dummy display and calls `.draw()` once. Prints `OK` lines and a final summary. This is the integration backstop the golden rule forbids putting in `tests/`.

- [ ] **Step 1: Write `TOOLS/smoke_dungeon.py`**

```python
# TOOLS/smoke_dungeon.py
"""Headless integration smoke for the SIM dungeon: run a full two-half crawl on the test
sim via CrawlSession + feed actuals, then construct and draw every new screen once.

Run:  .venv/Scripts/python TOOLS/smoke_dungeon.py
ASCII-only output. Uses the SDL dummy driver so it needs no display."""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from src.ui.app import App  # noqa: E402
from src.game.crawl import CrawlSession  # noqa: E402
from src.game.replay_feed import ReplayFeed  # noqa: E402
from src.game.normalize_soccer import actuals_from_raw  # noqa: E402
from src.game.score import total_tiles_game  # noqa: E402
from src.ui.flow import _pool_from_feed  # noqa: E402
from src.ui.sim import SimMode  # noqa: E402
from src.ui.screens.shop_screen import ShopScreen  # noqa: E402
from src.ui.screens.dungeon_play_screen import DungeonPlayScreen  # noqa: E402
from src.ui.screens.status_screens import DungeonFinalScreen  # noqa: E402
from src.utils.constants import CONFIG, load_data  # noqa: E402

_SIM = CONFIG["launcher"]["test_sim"]
_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_HALF_MIN = CONFIG["game"]["half_minutes"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_WINDOWS = CONFIG["game"]["windows_per_half"]


def _actuals(feed, half, window):
    start = (half - 1) * _HALF_MIN + (window - 1) * _WINDOW_MIN
    a = feed.snapshot_at(start)
    b = feed.snapshot_at(start + _WINDOW_MIN)
    raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
    return actuals_from_raw(raw, _STATS_MENU)


def main() -> None:
    feed = ReplayFeed.from_file(_SIM)
    pool = _pool_from_feed(feed)
    assert pool, "FAIL sim feed has no lineup"
    session = CrawlSession(party_size=1, pool=pool, rng=random.Random(99))
    print(f"OK loaded sim: {len(pool)} athletes, treasury {session.treasury}")

    # Auto-buy a weapon + armor if affordable.
    for category in ("weapon", "armor"):
        for item in session.catalog():
            if item.category == category and session.buy(0, item)[0]:
                print(f"OK bought {category}: {item.name} ({item.price}g)")
                break

    lines = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}
    for half in (1, 2):
        for window in range(1, _WINDOWS + 1):
            if session.half_over():
                break
            res = session.resolve_window([lines], _actuals(feed, half, window),
                                         f"H{half} W{window}")
            print(f"OK H{half} W{window}: +{res.tiles_advanced} tiles ({res.color}), "
                  f"depth {session.state.depth}, gold {session.treasury}")
        if half == 1:
            session.begin_second_half()
            print("OK begin second half")

    total = total_tiles_game(session.party_size)
    print(f"OK final score: {session.score_label()}")
    assert 0 <= session.percent() <= 100, "FAIL percent out of range"

    # Render-construction smoke: every new screen draws without raising.
    app = App()
    fresh = CrawlSession(party_size=1, pool=pool, rng=random.Random(99))
    ShopScreen(app, fresh, lambda: None, SimMode(True)).draw(app.screen)
    print("OK ShopScreen draws")
    play = DungeonPlayScreen(app, fresh, feed, 1, "First Half -- Window 1/3",
                             lambda ln: fresh.resolve_window([ln], _actuals(feed, 1, 1), "H1 W1"),
                             lambda: None, SimMode(True))
    play.draw(app.screen)
    play._descend()
    play.draw(app.screen)
    print("OK DungeonPlayScreen draws (both phases)")
    DungeonFinalScreen(app, session.percent(), session.cleared_total(), total).draw(app.screen)
    print("OK DungeonFinalScreen draws")
    print("OK smoke complete")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the smoke**

Run: `.venv/Scripts/python TOOLS/smoke_dungeon.py`
Expected: a sequence of `OK ...` lines ending in `OK smoke complete`, with no `FAIL` and no traceback. Depth should be > 0 after the windows and the final score line like `Depth NN/28 (PP%)`.

- [ ] **Step 3: Commit**

```bash
git add TOOLS/smoke_dungeon.py
git commit -m "test(tools): add headless dungeon SIM integration smoke

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Final verification + log

**Files:**
- Modify: `log.md`

- [ ] **Step 1: Run the full suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (273 passed).

- [ ] **Step 2: Run the smoke once more**

Run: `.venv/Scripts/python TOOLS/smoke_dungeon.py`
Expected: ends `OK smoke complete`, no FAIL.

- [ ] **Step 3: Launch check (close the window after it opens)**

Run: `.venv/Scripts/python src/main.py --dungeon`
Expected: the window opens on the splash, advances (SIM mode) to pre-game, then the shop. Press R in the shop to auto-buy + descend; predict and press the Descend/Continue buttons through both halves to the final % screen. No traceback in the console. Close the window.

- [ ] **Step 4: Append a line to `log.md`**

Add under today's date (ASCII only, format `YYYY-MM-DD | what | files`):

```
2026-06-22 | Plan 1b: SIM-mode dungeon UI (CrawlSession + shop/play/final screens + icons + flow); 273 tests pass; smoke OK | src/game/crawl.py, src/utils/asset_loader.py, TOOLS/make_icons.py, TOOLS/smoke_dungeon.py, src/ui/screens/shop_screen.py, src/ui/screens/dungeon_play_screen.py, src/ui/screens/status_screens.py, src/ui/widgets.py, src/ui/flow.py, src/main.py, config/*.json
```

- [ ] **Step 5: Commit**

```bash
git add log.md
git commit -m "docs(log): record Plan 1b SIM-mode dungeon UI completion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (design spec sections 12 + 13 + 15 + 16):

- Shop generated from match lineup, prices, shared treasury, loadout slots, buy/sell, one-two-handed enforcement -> Task 6 (uses Plan 1a `build_catalog`/`Loadout`/`CrawlSession.buy/sell`). COVERED.
- 15-minute windows, 3 per half, five stat predictions -> Task 7 dials + Task 9 `_window_actuals` (15-min boundaries) + `windows_per_half`. COVERED.
- Accuracy bands -> tiles, Power from goal predictions, monster gates, wounds -> handled by Plan 1a `resolve_window`, surfaced in Task 7 status line + Task 5 depth meter. COVERED.
- Window cells colored green/orange/red -> Task 7 `_draw_window_cells` using `session.window_colors`. COVERED.
- Depth meter with tile pips + gate markers -> Task 5 `draw_depth_meter`. COVERED.
- Scrollable crawl log -> Task 7 reuses `LogList`. COVERED.
- PNG icon set + loader -> Tasks 3 + 4 (nine icons, `load_icon` with fallback). COVERED.
- Party-size scaling + 1-3 party -> Plan 1a engine; SIM defaults to party_size=1 via `game.dungeon_party_size` (Task 1). Multi-fighter local input is deferred (single-device sim predicts for one fighter) — NOTED as out-of-scope for 1b; full party is Plan 2. COVERED (scaling present; multi-input deferred by design).
- Score = % dungeon completed -> Task 8 `DungeonFinalScreen` + `CrawlSession.percent`. COVERED.
- Sim mode runs full flow on one device, fixed seed, recorded World Cup -> Task 9 `DungeonSimFlow` + `start_dungeon_sim` + `--dungeon` + launcher option. COVERED.
- Second-half re-buy with price multiplier -> Task 9 `_on_continue` calls `begin_second_half` then `_to_shop`; `CrawlSession.catalog()` applies `second_half_multiplier`. COVERED.
- Smoke driving a full sim half -> Task 10 `TOOLS/smoke_dungeon.py` (both halves). COVERED.

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". The Task 1 deliberate-typo note (`dp_header_size`) is called out explicitly so it is not copied wrong. `update(self, dt)` bodies are intentionally `...` (no per-frame state to advance — matching `DraftScreen`/`status_screens` which also no-op). Clean.

**3. Type consistency:**
- `CrawlSession(party_size, pool, rng, ...)` — same constructor used in Tasks 2, 6, 7, 9, 10.
- `buy(member, item) -> (bool, str)`, `sell(member, item_id)`, `resolve_window(fighter_lines, actuals, window_label) -> WindowResult`, `catalog()`, `half_over()`, `begin_second_half()`, `match_over()`, `percent()`, `cleared_total()`, `score_label()`, `window_colors`, `state` — all referenced consistently.
- `draw_depth_meter(surface, rect, depth, total, gate_step, color_key)` — defined Task 5, called Task 7 with matching args.
- `load_icon(name) -> Optional[Surface]` — defined Task 3, called Tasks 6/7.
- `ShopScreen(app, session, on_done, sim=None, member=0)`, `DungeonPlayScreen(app, session, feed, window, label, on_descend, on_continue, sim=None)`, `DungeonFinalScreen(app, percent, depth, total, on_continue=None, title=...)` — constructed identically in flow (Task 9) and smoke (Task 10).
- `gate_step(half)` (Plan 1a) imported in Task 7 — matches `src/game/dungeon.py`.
- `total_tiles_game(party_size)` imported in Tasks 9/10 — matches `src/game/score.py`.

All consistent. Plan ready for execution.
