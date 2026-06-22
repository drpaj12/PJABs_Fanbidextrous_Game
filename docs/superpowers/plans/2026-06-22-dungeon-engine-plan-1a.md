# Dungeon Engine (Plan 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure, headless dungeon-crawl engine (accuracy bands -> tiles, goal->Power, monster gates with dice, gold economy, item catalog from the real lineup, per-fighter loadout, % -completed scoring, and the leader-authoritative window resolver) entirely under `src/game/` with full pytest coverage and zero pygame.

**Architecture:** Each mechanic is a small pure module in `src/game/` reading its constants from `config/game_config.json` via `src/utils/constants.py`. A single `window_resolver.resolve_window(...)` orchestrates one 15-minute window: it grades every fighter's predictions into bands, sums them into tile advancement, accrues Power from correct goal predictions, advances the party along a linear tile track, resolves any monster gate it crosses with an injected RNG, and awards gold. All randomness flows through an injected `rng` object (`random.Random` in production) so it is deterministic and testable. No UI, no relay — those are Plans 1b and 2.

**Tech Stack:** Python 3.11, pytest. Run Python as `.venv/Scripts/python` and pytest as `.venv/Scripts/python -m pytest`. NEVER use bare `python`. All output/log strings are ASCII-only.

**Reference:** Full design at `docs/superpowers/specs/2026-06-22-dungeon-crawl-redesign-design.md`.

---

## File Structure (what each new file owns)

Pure modules (`src/game/`, zero pygame):
- `bands.py` — grade a progress-stat prediction into a `Band` (step-points); compute window color.
- `power.py` — Power gained from a goal prediction (never for a predicted 0).
- `score.py` — tile totals per half / per game; percent-completed.
- `items.py` — generate the item catalog from the match's `DraftedAthlete` lineup + templates.
- `loadout.py` — a fighter's up-to-6-item loadout, constraints, and derived combat bonuses.
- `treasury.py` — gold awards (per tile, gate loot, base treasury) and the half price multiplier.
- `dungeon.py` — `DungeonState`, gate spacing, monster difficulty, and a single gate dice resolution.
- `window_resolver.py` — orchestrates one window end-to-end (the leader-authoritative resolution).

Data/config:
- `assets/data/item_templates.json` — naming templates + price/effect formulas per item category.
- `config/game_config.json` — new `bands`, `power`, `dungeon`, `economy` blocks + `game` updates.

Tests (`tests/`, pure): one file per module plus a full-half integration test.

Dependency direction: `score` <- `dungeon` <- `window_resolver`; `items` <- `loadout` <- `window_resolver`; `bands`, `power`, `treasury` are leaves. No module imports pygame or `src/ui`.

---

## Task 1: Config blocks + item templates

**Files:**
- Modify: `config/game_config.json` (the `game` block; add `bands`, `power`, `dungeon`, `economy`)
- Create: `assets/data/item_templates.json`
- Test: `tests/test_dungeon_config.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_dungeon_config.py
"""Config-shape guards for the dungeon redesign."""
from src.utils.constants import CONFIG, load_data


def test_window_timing_is_fifteen_minutes():
    g = CONFIG["game"]
    assert g["window_seconds"] == 900
    assert g["windows_per_half"] == 3
    assert g["half_minutes"] * 60 // g["window_seconds"] == g["windows_per_half"]
    assert g["loadout_size"] == 6


def test_band_blocks_present_and_ordered():
    b = CONFIG["bands"]
    assert b["order"] == ["exact", "close", "near", "off", "big_miss"]
    assert b["exact"]["step"] == 3 and b["big_miss"]["step"] == -1
    assert b["window_color"]["green_min"] == 8 and b["window_color"]["red_max"] == 2


def test_power_dungeon_economy_blocks_present():
    assert CONFIG["power"]["min_predicted"] == 1
    assert CONFIG["dungeon"]["dice_sides"] == 6
    assert CONFIG["dungeon"]["max_wounds"] == 3
    assert CONFIG["economy"]["base_treasury_per_fighter"] == 300


def test_item_templates_cover_every_category():
    t = load_data("assets/data/item_templates.json")
    for cat in ("weapon", "armor", "consumable", "magic"):
        assert t[cat]["names"], cat
    assert t["weapon"]["two_handed"] is True
    assert t["magic"]["effect"]["options"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon_config.py -v`
Expected: FAIL — `KeyError: 'windows_per_half'` (and missing blocks).

- [x] **Step 3: Edit `config/game_config.json`**

In the `"game"` block, change `"window_seconds": 300` to `900`, and add `"windows_per_half": 3` and `"loadout_size": 6`. Then add these four top-level blocks (anywhere after `"game"`):

```json
  "bands": {
    "_comment": "Progress-stat accuracy bands by absolute error; step = tiles advanced.",
    "order": ["exact", "close", "near", "off", "big_miss"],
    "exact":    {"max_diff": 0,   "step": 3,  "label": "EXACT"},
    "close":    {"max_diff": 1,   "step": 2,  "label": "CLOSE"},
    "near":     {"max_diff": 2,   "step": 1,  "label": "NEAR"},
    "off":      {"max_diff": 4,   "step": 0,  "label": "OFF"},
    "big_miss": {"max_diff": 999, "step": -1, "label": "BIG MISS"},
    "window_color": {"green_min": 8, "red_max": 2}
  },
  "power": {
    "_comment": "Goal prediction grants persistent Power; never for a predicted line below min_predicted.",
    "exact_gain": 2,
    "close_gain": 1,
    "close_max_diff": 1,
    "min_predicted": 1,
    "roll_bonus_per_power": 1,
    "gold_bonus_per_power": 0.10
  },
  "dungeon": {
    "tiles_per_fighter_half1": 12,
    "tiles_per_fighter_half2": 16,
    "gate_every_tiles_half1": 8,
    "gate_every_tiles_half2": 6,
    "monster_base_difficulty_half1": 6,
    "monster_base_difficulty_half2": 8,
    "monster_difficulty_per_fighter": 1,
    "monster_difficulty_per_threat": 1,
    "dice_sides": 6,
    "max_wounds": 3,
    "tiles_lost_per_unsoaked_point": 1
  },
  "economy": {
    "base_treasury_per_fighter": 300,
    "gold_per_tile": 5,
    "gold_depth_bonus_per_gate": 3,
    "gate_loot": 50,
    "second_half_price_multiplier": 1.5
  },
```

- [x] **Step 4: Create `assets/data/item_templates.json`**

```json
{
  "_comment": "Naming templates + price/effect formulas. The actual catalog is generated per-match from the lineup (see src/game/items.py). {sur} = player surname.",
  "weapon": {
    "names": ["Sword of {sur}", "Blade of {sur}", "Spear of {sur}", "Axe of {sur}"],
    "two_handed": true,
    "price":  {"base": 120, "per_star": 40},
    "effect": {"kind": "dice_bonus", "base": 1, "per_star": 1}
  },
  "armor": {
    "names": ["Aegis of {sur}", "Helm of {sur}", "Bulwark of {sur}", "Mail of {sur}"],
    "two_handed": false,
    "price":  {"base": 90, "per_star": 30},
    "effect": {"kind": "soak", "base": 1, "per_star": 1}
  },
  "consumable": {
    "names": ["{sur}'s Potion of Haste", "{sur}'s Draught of Valor", "{sur}'s Elixir of Passage"],
    "two_handed": false,
    "price":  {"base": 40, "per_star": 15},
    "effect": {"kind": "auto_pass_or_roll", "base": 2, "per_star": 1}
  },
  "magic": {
    "names": ["{sur}'s Amulet of Fortune", "{sur}'s Charm of Warding", "{sur}'s Sigil of Power"],
    "two_handed": false,
    "price":  {"base": 150, "per_star": 50},
    "effect": {"kind": "magic", "options": ["gold", "reroll", "power", "extra_slot"]}
  }
}
```

- [x] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon_config.py -v`
Expected: PASS (4 tests).

- [x] **Step 6: Confirm nothing else broke from the window_seconds change**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS. (Window timing is config-driven; if any test hard-codes the old 300/9-window assumption, update that test's expected values to the 900/3-window reality — do not reintroduce magic numbers.)

- [x] **Step 7: Commit**

```bash
git add config/game_config.json assets/data/item_templates.json tests/test_dungeon_config.py
git commit -m "feat: dungeon config blocks + item templates + 15-min windows"
```

---

## Task 2: `bands.py` — accuracy bands + window color

**Files:**
- Create: `src/game/bands.py`
- Test: `tests/test_bands.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_bands.py
from src.game.bands import Band, grade_progress, window_color


def test_exact_close_near():
    assert grade_progress(3, 3).key == "exact" and grade_progress(3, 3).step == 3
    assert grade_progress(3, 4).key == "close" and grade_progress(3, 4).step == 2
    assert grade_progress(3, 5).key == "near" and grade_progress(3, 5).step == 1


def test_off_and_big_miss():
    assert grade_progress(3, 7).key == "off" and grade_progress(3, 7).step == 0   # diff 4
    b = grade_progress(0, 7)                                                       # diff 7
    assert b.key == "big_miss" and b.step == -1 and b.is_big_miss is True


def test_window_color_thresholds():
    assert window_color(8, False) == "green"
    assert window_color(5, False) == "orange"
    assert window_color(2, False) == "red"
    assert window_color(10, True) == "red"   # any big miss forces red
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_bands.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.bands'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/bands.py
"""Grade a progress-stat prediction into an accuracy band (tile step-points) and color a window."""
from dataclasses import dataclass

from src.utils.constants import CONFIG

_B = CONFIG["bands"]


@dataclass(frozen=True)
class Band:
    key: str
    step: int
    label: str
    is_big_miss: bool


def grade_progress(line: int, actual: int) -> Band:
    """Return the band for one progress stat by absolute error |line - actual|."""
    diff = abs(int(line) - int(actual))
    for key in _B["order"]:
        spec = _B[key]
        if diff <= spec["max_diff"]:
            return Band(key=key, step=int(spec["step"]), label=spec["label"],
                        is_big_miss=(key == "big_miss"))
    spec = _B["big_miss"]
    return Band(key="big_miss", step=int(spec["step"]), label=spec["label"], is_big_miss=True)


def window_color(tiles: int, has_big_miss: bool) -> str:
    """green for a strong window, red for a weak/failed one, orange otherwise."""
    wc = _B["window_color"]
    if has_big_miss or tiles <= wc["red_max"]:
        return "red"
    if tiles >= wc["green_min"]:
        return "green"
    return "orange"
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_bands.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/bands.py tests/test_bands.py
git commit -m "feat: accuracy bands + window color"
```

---

## Task 3: `power.py` — goal-prediction Power

**Files:**
- Create: `src/game/power.py`
- Test: `tests/test_power.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_power.py
from src.game.power import power_gain


def test_predicting_zero_never_grants_power():
    assert power_gain(0, 0) == 0
    assert power_gain(0, 5) == 0


def test_exact_and_close_bands():
    assert power_gain(2, 2) == 2   # exact, predicted >= 1
    assert power_gain(2, 3) == 1   # close (diff 1)
    assert power_gain(2, 1) == 1   # close (diff 1)


def test_far_goal_prediction_grants_nothing():
    assert power_gain(2, 5) == 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_power.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.power'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/power.py
"""Power gained from a window's goal prediction. Persists for the rest of the crawl."""
from src.utils.constants import CONFIG

_P = CONFIG["power"]


def power_gain(predicted_line: int, actual: int) -> int:
    """Power for one goal prediction. A predicted line below min_predicted (e.g. 0) earns nothing,
    even when correct -- the safe pick grants no power."""
    if int(predicted_line) < _P["min_predicted"]:
        return 0
    diff = abs(int(predicted_line) - int(actual))
    if diff == 0:
        return int(_P["exact_gain"])
    if diff <= _P["close_max_diff"]:
        return int(_P["close_gain"])
    return 0
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_power.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/power.py tests/test_power.py
git commit -m "feat: goal-prediction Power"
```

---

## Task 4: `score.py` — tile totals + percent complete

**Files:**
- Create: `src/game/score.py`
- Test: `tests/test_score.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_score.py
from src.game.score import percent_complete, total_tiles_game, total_tiles_half


def test_tile_totals_scale_with_party_size():
    assert total_tiles_half(1, 1) == 12
    assert total_tiles_half(2, 1) == 16
    assert total_tiles_half(1, 3) == 36
    assert total_tiles_game(3) == (12 + 16) * 3   # 84


def test_percent_complete_clamps_and_rounds():
    assert percent_complete(0, 3) == 0
    assert percent_complete(42, 3) == 50          # 42 / 84
    assert percent_complete(100, 3) == 100        # clamped to total
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.score'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/score.py
"""Dungeon tile totals (party-size scaled) and the party's percent-completed score."""
from src.utils.constants import CONFIG

_D = CONFIG["dungeon"]


def total_tiles_half(half: int, party_size: int) -> int:
    key = "tiles_per_fighter_half1" if half == 1 else "tiles_per_fighter_half2"
    return int(_D[key]) * int(party_size)


def total_tiles_game(party_size: int) -> int:
    return total_tiles_half(1, party_size) + total_tiles_half(2, party_size)


def percent_complete(depth_done: int, party_size: int) -> int:
    """depth_done = cumulative tiles cleared across both halves. Returns 0..100."""
    total = total_tiles_game(party_size)
    if total <= 0:
        return 0
    return round(100 * min(int(depth_done), total) / total)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_score.py -v`
Expected: PASS (2 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/score.py tests/test_score.py
git commit -m "feat: tile totals + percent-completed score"
```

---

## Task 5: `items.py` — catalog generated from the lineup

**Files:**
- Create: `src/game/items.py`
- Test: `tests/test_items.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_items.py
from src.game.athlete import DraftedAthlete
from src.game.items import Item, build_catalog, build_item


def _ath(aid, name, pos):
    return DraftedAthlete.create(athlete_id=aid, name=name, broad_position=pos, team="X", jersey=9)


def test_position_maps_to_category_and_names_use_surname():
    w = build_item(_ath("a1", "Lionel Messi", "Attacker"), half=1, price_multiplier=1.0)
    assert w.category == "weapon" and w.two_handed is True and w.persist == "infinite"
    assert "Messi" in w.name
    c = build_item(_ath("m1", "Luka Modric", "Midfielder"), half=1, price_multiplier=1.0)
    assert c.category == "consumable" and c.persist == "round" and "Modric" in c.name


def test_price_scales_with_half_multiplier():
    a = _ath("a1", "Lionel Messi", "Attacker")
    base = build_item(a, half=1, price_multiplier=1.0).price
    h2 = build_item(a, half=2, price_multiplier=1.5).price
    assert h2 == round(base * 1.5)


def test_effect_value_and_deterministic_magic_option():
    gk = _ath("g1", "Manuel Neuer", "Goalkeeper")
    one = build_item(gk, 1, 1.0)
    two = build_item(gk, 1, 1.0)
    assert one.category == "magic" and one.effect["kind"] == "magic"
    assert one.effect["option"] == two.effect["option"]      # deterministic by athlete_id
    wpn = build_item(_ath("a2", "Kylian Mbappe", "Attacker"), 1, 1.0)
    assert wpn.effect["kind"] == "dice_bonus" and wpn.effect["value"] >= 1


def test_build_catalog_one_item_per_athlete():
    pool = [_ath("a1", "Lionel Messi", "Attacker"), _ath("d1", "Paolo Maldini", "Defender")]
    cat = build_catalog(pool, half=1, price_multiplier=1.0)
    assert len(cat) == 2
    assert {i.category for i in cat} == {"weapon", "armor"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_items.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.items'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/items.py
"""Generate the shop catalog from the current match's lineup. One item per athlete,
mapped by position; name/price/effect derived from the player and the templates so items
always relate to who is actually playing."""
import hashlib
from dataclasses import dataclass

from src.game.athlete import DraftedAthlete
from src.utils.constants import load_data

_TEMPLATES = load_data("assets/data/item_templates.json")
_POS_CATEGORY = {
    "Attacker": "weapon",
    "Defender": "armor",
    "Midfielder": "consumable",
    "Goalkeeper": "magic",
}
_PERSIST = {"weapon": "infinite", "armor": "infinite",
            "consumable": "round", "magic": "infinite"}


def _stable_index(text: str, n: int) -> int:
    """Deterministic across processes/clients (unlike Python's salted hash())."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % n


def _surname(name: str) -> str:
    parts = name.split()
    return parts[-1] if parts else name


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    category: str
    price: int
    two_handed: bool
    persist: str
    effect: dict
    source_pos: str
    stars: int


def _effect(category: str, stars: int, item_id: str) -> dict:
    t = _TEMPLATES[category]["effect"]
    if category == "magic":
        opts = t["options"]
        return {"kind": "magic", "option": opts[_stable_index("magic:" + item_id, len(opts))]}
    return {"kind": t["kind"], "value": int(t["base"] + t["per_star"] * stars)}


def build_item(athlete: DraftedAthlete, half: int, price_multiplier: float) -> Item:
    category = _POS_CATEGORY.get(athlete.broad_position, "consumable")
    tmpl = _TEMPLATES[category]
    names = tmpl["names"]
    name = names[_stable_index("name:" + athlete.athlete_id, len(names))].format(sur=_surname(athlete.name))
    base_price = tmpl["price"]["base"] + tmpl["price"]["per_star"] * athlete.stars
    return Item(
        item_id=athlete.athlete_id,
        name=name,
        category=category,
        price=int(round(base_price * price_multiplier)),
        two_handed=bool(tmpl.get("two_handed", False)),
        persist=_PERSIST[category],
        effect=_effect(category, athlete.stars, athlete.athlete_id),
        source_pos=athlete.broad_position,
        stars=athlete.stars,
    )


def build_catalog(athletes: list[DraftedAthlete], half: int = 1,
                  price_multiplier: float = 1.0) -> list[Item]:
    return [build_item(a, half, price_multiplier) for a in athletes]
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_items.py -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/items.py tests/test_items.py
git commit -m "feat: item catalog generated from lineup"
```

---

## Task 6: `loadout.py` — per-fighter loadout + combat bonuses

**Files:**
- Create: `src/game/loadout.py`
- Test: `tests/test_loadout.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_loadout.py
from src.game.items import Item
from src.game.loadout import Loadout


def _item(iid, category, value=2, two_handed=False, option=None, price=100):
    effect = {"kind": "magic", "option": option} if category == "magic" else {"kind": "x", "value": value}
    return Item(item_id=iid, name=iid, category=category, price=price, two_handed=two_handed,
                persist="infinite", effect=effect, source_pos="X", stars=3)


def test_only_one_two_handed_weapon():
    lo = Loadout()
    lo.add(_item("w1", "weapon", two_handed=True))
    ok, reason = lo.can_add(_item("w2", "weapon", two_handed=True))
    assert ok is False and "weapon" in reason


def test_slot_cap_and_extra_slot_magic():
    lo = Loadout()
    for i in range(6):
        lo.add(_item(f"a{i}", "armor"))
    assert lo.can_add(_item("a6", "armor"))[0] is False         # cap 6 reached
    lo2 = Loadout()
    lo2.add(_item("ms", "magic", option="extra_slot"))           # raises cap to 7
    for i in range(6):
        lo2.add(_item(f"a{i}", "armor"))
    assert len(lo2.items) == 7


def test_best_bonuses_and_total_cost():
    lo = Loadout()
    lo.add(_item("w1", "weapon", value=3, two_handed=True, price=200))
    lo.add(_item("ar", "armor", value=2, price=90))
    lo.add(_item("mg", "magic", option="reroll", price=150))
    assert lo.best_weapon_bonus() == 3
    assert lo.best_armor_soak() == 2
    assert lo.has_reroll() is True
    assert lo.total_cost() == 440
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_loadout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.loadout'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/loadout.py
"""A single fighter's loadout: up to loadout_size items, at most one two-handed weapon,
extra-slot magic raises the cap. Exposes the combat bonuses the dungeon resolver needs."""
from dataclasses import dataclass, field

from src.game.items import Item
from src.utils.constants import CONFIG

_BASE_CAP = int(CONFIG["game"]["loadout_size"])


@dataclass
class Loadout:
    items: list = field(default_factory=list)

    def slot_cap(self) -> int:
        extra = sum(1 for it in self.items
                    if it.category == "magic" and it.effect.get("option") == "extra_slot")
        return _BASE_CAP + extra

    def has_weapon(self) -> bool:
        return any(it.category == "weapon" for it in self.items)

    def can_add(self, item: Item) -> tuple[bool, str]:
        if any(it.item_id == item.item_id for it in self.items):
            return False, "already owned"
        if item.category == "weapon" and item.two_handed and self.has_weapon():
            return False, "only one two-handed weapon"
        if len(self.items) >= self.slot_cap():
            return False, "no free slot"
        return True, ""

    def add(self, item: Item) -> None:
        ok, reason = self.can_add(item)
        if not ok:
            raise ValueError(reason)
        self.items.append(item)

    def remove(self, item_id: str) -> None:
        self.items = [it for it in self.items if it.item_id != item_id]

    def total_cost(self) -> int:
        return sum(it.price for it in self.items)

    def best_weapon_bonus(self) -> int:
        vals = [it.effect.get("value", 0) for it in self.items if it.category == "weapon"]
        return max(vals) if vals else 0

    def best_armor_soak(self) -> int:
        vals = [it.effect.get("value", 0) for it in self.items if it.category == "armor"]
        return max(vals) if vals else 0

    def has_reroll(self) -> bool:
        return any(it.category == "magic" and it.effect.get("option") == "reroll"
                   for it in self.items)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_loadout.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/loadout.py tests/test_loadout.py
git commit -m "feat: per-fighter loadout + combat bonuses"
```

---

## Task 7: `treasury.py` — gold awards

**Files:**
- Create: `src/game/treasury.py`
- Test: `tests/test_treasury.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_treasury.py
from src.game.treasury import base_treasury, gate_loot_gold, second_half_multiplier, tile_gold


def test_base_treasury_scales_with_party():
    assert base_treasury(1) == 300
    assert base_treasury(3) == 900


def test_tile_gold_grows_with_gates_and_power():
    assert tile_gold(gates_passed=0, power=0) == 5
    assert tile_gold(gates_passed=1, power=0) == 8          # 5 + 3
    assert tile_gold(gates_passed=0, power=10) == 10        # 5 * (1 + 0.10*10) = 10


def test_gate_loot_and_multiplier():
    assert gate_loot_gold(power=0) == 50
    assert gate_loot_gold(power=10) == 100                  # 50 * 2
    assert second_half_multiplier() == 1.5
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_treasury.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.treasury'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/treasury.py
"""Gold awards: base party treasury, per-tile gold (deeper + Power = richer), gate loot,
and the second-half price multiplier."""
from src.utils.constants import CONFIG

_E = CONFIG["economy"]
_GBP = CONFIG["power"]["gold_bonus_per_power"]


def base_treasury(party_size: int) -> int:
    return int(_E["base_treasury_per_fighter"]) * int(party_size)


def _power_mult(power: int) -> float:
    return 1.0 + _GBP * power


def tile_gold(gates_passed: int, power: int) -> int:
    base = _E["gold_per_tile"] + _E["gold_depth_bonus_per_gate"] * gates_passed
    return int(round(base * _power_mult(power)))


def gate_loot_gold(power: int) -> int:
    return int(round(_E["gate_loot"] * _power_mult(power)))


def second_half_multiplier() -> float:
    return float(_E["second_half_price_multiplier"])
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_treasury.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/treasury.py tests/test_treasury.py
git commit -m "feat: gold treasury awards"
```

---

## Task 8: `dungeon.py` — state, difficulty, gate dice

**Files:**
- Create: `src/game/dungeon.py`
- Test: `tests/test_dungeon.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_dungeon.py
from src.game.dungeon import (DungeonState, gate_step, monster_difficulty, resolve_gate)


class SeqRng:
    """Deterministic stand-in for random.Random: returns queued randint values in order."""
    def __init__(self, values):
        self._v = list(values)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i % len(self._v)]
        self._i += 1
        return v


def test_state_total_tiles_and_helpers():
    st = DungeonState(half=1, party_size=3)
    assert st.total_tiles == 36
    assert gate_step(1) == 8 and gate_step(2) == 6
    assert monster_difficulty(1, 3, 0) == 8        # 6 + 1*(3-1)
    assert monster_difficulty(1, 1, 2) == 8        # 6 + 0 + 1*2 threat


def test_gate_pass_with_weapon_and_power():
    rng = SeqRng([3])                               # base roll 3
    out = resolve_gate(rng, weapon_bonus=4, armor_soak=0, power=1, half=1,
                       party_size=1, threat=0)      # diff 6; 3+4+1 = 8 >= 6
    assert out.passed is True and out.roll == 8 and out.difficulty == 6


def test_gate_fail_soak_reduces_tiles_lost():
    rng = SeqRng([1])                               # base roll 1
    out = resolve_gate(rng, weapon_bonus=0, armor_soak=2, power=0, half=1,
                       party_size=1, threat=0)      # diff 6; roll 1; shortfall 5; soak 2
    assert out.passed is False and out.soaked == 2 and out.tiles_lost == 3 and out.wound is True


def test_reroll_takes_second_die_on_fail():
    rng = SeqRng([1, 6])                            # first roll fails, reroll = 6
    out = resolve_gate(rng, weapon_bonus=0, armor_soak=0, power=0, half=1,
                       party_size=1, threat=0, reroll=True)   # diff 6; reroll 6 >= 6
    assert out.passed is True and out.roll == 6
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.dungeon'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/dungeon.py
"""Linear dungeon depth track: party state, gate spacing, monster difficulty, and a single
seeded gate dice resolution. All randomness comes from the injected rng (random.Random)."""
from dataclasses import dataclass

from src.game.score import total_tiles_half
from src.utils.constants import CONFIG

_D = CONFIG["dungeon"]
_ROLL_BONUS_PER_POWER = int(CONFIG["power"]["roll_bonus_per_power"])


@dataclass
class DungeonState:
    half: int
    party_size: int
    depth: int = 0
    power: int = 0
    wounds: int = 0
    threat: int = 0
    gates_passed: int = 0
    finished: bool = False

    @property
    def total_tiles(self) -> int:
        return total_tiles_half(self.half, self.party_size)


def gate_step(half: int) -> int:
    return int(_D["gate_every_tiles_half1"] if half == 1 else _D["gate_every_tiles_half2"])


def monster_difficulty(half: int, party_size: int, threat: int) -> int:
    base = _D["monster_base_difficulty_half1"] if half == 1 else _D["monster_base_difficulty_half2"]
    return int(base
               + _D["monster_difficulty_per_fighter"] * (party_size - 1)
               + _D["monster_difficulty_per_threat"] * threat)


@dataclass(frozen=True)
class GateOutcome:
    passed: bool
    roll: int
    difficulty: int
    soaked: int
    tiles_lost: int
    wound: bool


def resolve_gate(rng, weapon_bonus: int, armor_soak: int, power: int, half: int,
                 party_size: int, threat: int, consumable_value: int = 0,
                 reroll: bool = False) -> GateOutcome:
    """Roll d(dice_sides) + weapon + Power*roll_bonus + consumable vs monster difficulty.
    On a failed roll, reroll (if available) once, then armor soaks the shortfall; any leftover
    costs tiles and inflicts a wound."""
    diff = monster_difficulty(half, party_size, threat)
    sides = int(_D["dice_sides"])
    bonus = weapon_bonus + _ROLL_BONUS_PER_POWER * power + consumable_value
    roll = rng.randint(1, sides) + bonus
    if roll < diff and reroll:
        roll = rng.randint(1, sides) + bonus
    if roll >= diff:
        return GateOutcome(True, roll, diff, 0, 0, False)
    shortfall = diff - roll
    soaked = min(armor_soak, shortfall)
    tiles_lost = (shortfall - soaked) * int(_D["tiles_lost_per_unsoaked_point"])
    return GateOutcome(False, roll, diff, soaked, tiles_lost, True)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon.py -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/dungeon.py tests/test_dungeon.py
git commit -m "feat: dungeon state + gate dice resolution"
```

---

## Task 9: `window_resolver.py` — orchestrate one window

**Files:**
- Create: `src/game/window_resolver.py`
- Test: `tests/test_window_resolver.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_window_resolver.py
from src.game.dungeon import DungeonState
from src.game.window_resolver import PartyGear, resolve_window


class SeqRng:
    def __init__(self, values):
        self._v = list(values)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i % len(self._v)]
        self._i += 1
        return v


def _exact_lines(goal):
    # progress stats all predicted to match the actuals below -> 4 * exact (3) = +12 tiles
    return {"goal": goal, "shot": 3, "corner": 2, "card": 1, "foul": 4}


ACTUALS = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}


def test_all_exact_one_fighter_advances_and_passes_gate():
    st = DungeonState(half=1, party_size=1)         # total 12, gate at 8
    gear = PartyGear(weapon_bonus=5, armor_soak=0, has_reroll=False, consumable_value=0)
    rng = SeqRng([6])                               # gate roll 6 + weapon 5 = 11 >= diff 6
    res = resolve_window(rng, st, gear, [_exact_lines(2)], ACTUALS, "W1 @15'")
    assert res.tiles_advanced == 12
    assert res.power_gained == 2                    # goal exact, predicted >= 1
    assert st.power == 2
    assert st.gates_passed == 1
    assert st.depth == 12 and st.finished is True   # reached total
    assert res.color == "green"
    assert any("PASS" in line for line in res.log)


def test_big_miss_forces_red_and_raises_threat():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=9, armor_soak=0)
    rng = SeqRng([6])
    lines = {"goal": 0, "shot": 99, "corner": 2, "card": 1, "foul": 4}   # shot big miss
    res = resolve_window(rng, st, gear, [lines], ACTUALS, "W1")
    assert res.color == "red"
    assert st.threat == 1
    assert res.power_gained == 0                    # predicted 0 goals -> no power


def test_gate_fail_costs_tiles_and_wound():
    st = DungeonState(half=1, party_size=1)
    gear = PartyGear(weapon_bonus=0, armor_soak=0)
    rng = SeqRng([1])                               # roll 1 vs diff 6 -> fail, shortfall 5
    res = resolve_window(rng, st, gear, [_exact_lines(0)], ACTUALS, "W1")
    # advanced to gate (8) then lost 5 tiles -> depth 3, one wound
    assert st.wounds == 1 and st.depth == 3
    assert any("FAIL" in line for line in res.log)
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_window_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.game.window_resolver'`.

- [x] **Step 3: Write the implementation**

```python
# src/game/window_resolver.py
"""Leader-authoritative resolution of one 15-minute window: grade every fighter's predictions
into bands -> tile advance, accrue Power from goal predictions, walk the party along the tile
track resolving any monster gate crossed, and award gold. Pure: rng is injected."""
from dataclasses import dataclass, field

from src.game.bands import grade_progress, window_color
from src.game.dungeon import DungeonState, gate_step, resolve_gate
from src.game.power import power_gain
from src.game.treasury import gate_loot_gold, tile_gold
from src.utils.constants import CONFIG

_PROGRESS = ["shot", "corner", "card", "foul"]
_MAX_WOUNDS = int(CONFIG["dungeon"]["max_wounds"])


@dataclass
class PartyGear:
    """Party-wide combat aids for this window (best weapon/armor across fighters, one queued
    consumable value, reroll availability). Filled by the caller from the fighters' loadouts."""
    weapon_bonus: int = 0
    armor_soak: int = 0
    has_reroll: bool = False
    consumable_value: int = 0


@dataclass(frozen=True)
class WindowResult:
    tiles_advanced: int
    power_gained: int
    color: str
    gold: int
    gates: list = field(default_factory=list)
    log: list = field(default_factory=list)
    finished: bool = False


def resolve_window(rng, state: DungeonState, gear: PartyGear, fighter_lines: list,
                   actuals: dict, window_label: str) -> WindowResult:
    log: list = []
    tiles = 0
    has_big_miss = False
    power_gained = 0

    for lines in fighter_lines:
        for stat in _PROGRESS:
            band = grade_progress(int(lines.get(stat, 0)), int(actuals.get(stat, 0)))
            tiles += band.step
            if band.is_big_miss:
                has_big_miss = True
        power_gained += power_gain(int(lines.get("goal", 0)), int(actuals.get("goal", 0)))

    state.power += power_gained
    if has_big_miss:
        state.threat += 1
    color = window_color(tiles, has_big_miss)
    log.append(f"{window_label}  party advance +{tiles} ({color.upper()})")
    if power_gained:
        log.append(f"  POWER  goal -> +{power_gained} Power (now {state.power})")

    gold = 0
    gates: list = []
    step = gate_step(state.half)

    if tiles <= 0:
        state.depth = max(0, state.depth + tiles)
    else:
        remaining = tiles
        while remaining > 0 and not state.finished:
            next_gate = ((state.depth // step) + 1) * step
            advance = min(remaining, next_gate - state.depth)
            for _ in range(advance):
                state.depth += 1
                gold += tile_gold(state.gates_passed, state.power)
                if state.depth >= state.total_tiles:
                    state.finished = True
                    break
            remaining -= advance
            if state.finished:
                break
            if state.depth == next_gate:
                outcome = resolve_gate(
                    rng, gear.weapon_bonus, gear.armor_soak, state.power,
                    state.half, state.party_size, state.threat,
                    consumable_value=gear.consumable_value, reroll=gear.has_reroll)
                gear.consumable_value = 0   # spent at this gate
                gates.append(outcome)
                if outcome.passed:
                    state.gates_passed += 1
                    loot = gate_loot_gold(state.power)
                    gold += loot
                    log.append(f"  GATE   diff {outcome.difficulty} roll {outcome.roll} -> PASS +{loot}g")
                else:
                    state.depth = max(0, state.depth - outcome.tiles_lost)
                    state.wounds += 1
                    log.append(
                        f"  GATE   diff {outcome.difficulty} roll {outcome.roll} -> FAIL "
                        f"(soak {outcome.soaked}, -{outcome.tiles_lost} tiles, wound {state.wounds})")
                    if state.wounds >= _MAX_WOUNDS:
                        state.finished = True
                        log.append("  CRAWL  party downed -- half ends")
                    # A failed gate halts the party: remaining tiles this window are forfeited.
                    break

    log.append(f"  DEPTH  {state.depth}/{state.total_tiles}")
    return WindowResult(tiles_advanced=tiles, power_gained=power_gained, color=color,
                        gold=gold, gates=gates, log=log, finished=state.finished)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_window_resolver.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add src/game/window_resolver.py tests/test_window_resolver.py
git commit -m "feat: window resolver (leader-authoritative window resolution)"
```

---

## Task 10: Full-half integration test (engine end-to-end, headless)

**Files:**
- Test: `tests/test_dungeon_integration.py`

- [x] **Step 1: Write the integration test**

```python
# tests/test_dungeon_integration.py
"""Play a full 3-window half through the pure engine: build a catalog from a demo lineup,
equip a fighter, resolve three windows, and assert the party descends and scores a percent."""
import random

from src.game.athlete import DraftedAthlete
from src.game.dungeon import DungeonState
from src.game.items import build_catalog
from src.game.loadout import Loadout
from src.game.score import percent_complete
from src.game.treasury import base_treasury
from src.game.window_resolver import PartyGear, resolve_window


def _pool():
    specs = [("a1", "Lionel Messi", "Attacker"), ("d1", "Paolo Maldini", "Defender"),
             ("m1", "Luka Modric", "Midfielder"), ("g1", "Manuel Neuer", "Goalkeeper")]
    return [DraftedAthlete.create(athlete_id=a, name=n, broad_position=p, team="X", jersey=9)
            for a, n, p in specs]


def _gear_from(loadout: Loadout) -> PartyGear:
    return PartyGear(weapon_bonus=loadout.best_weapon_bonus(),
                     armor_soak=loadout.best_armor_soak(),
                     has_reroll=loadout.has_reroll())


def test_full_half_descent_and_score():
    party_size = 1
    treasury = base_treasury(party_size)
    assert treasury == 300

    catalog = build_catalog(_pool(), half=1, price_multiplier=1.0)
    weapon = next(i for i in catalog if i.category == "weapon")
    armor = next(i for i in catalog if i.category == "armor")
    loadout = Loadout()
    # A fighter cannot fully kit out on the base treasury; buy the weapon (it drives
    # gate-passing) and only add armor if it still fits the budget.
    loadout.add(weapon)
    if loadout.total_cost() + armor.price <= treasury:
        loadout.add(armor)
    treasury -= loadout.total_cost()
    assert treasury >= 0

    state = DungeonState(half=1, party_size=party_size)
    rng = random.Random(99)                      # deterministic
    actuals = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}
    good = {"goal": 2, "shot": 3, "corner": 2, "card": 1, "foul": 4}   # all exact

    total_gold = 0
    for w in range(1, 4):
        gear = _gear_from(loadout)
        res = resolve_window(rng, state, gear, [good], actuals, f"W{w}")
        total_gold += res.gold
        if state.finished:
            break

    assert state.depth > 0
    assert state.depth <= state.total_tiles
    assert total_gold > 0
    pct = percent_complete(state.depth, party_size)
    assert 0 < pct <= 100


def test_party_size_scaling_keeps_completion_comparable():
    # A 3-fighter party advances ~3x faster through a ~3x-longer dungeon, so the same per-fighter
    # quality of play yields a comparable percent.
    from src.game.score import total_tiles_half
    assert total_tiles_half(1, 3) == 3 * total_tiles_half(1, 1)
```

- [x] **Step 2: Run the integration test**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon_integration.py -v`
Expected: PASS (2 tests).

- [x] **Step 3: Run the whole suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (all prior tests + the ~9 new test files for this plan).

- [x] **Step 4: Commit**

```bash
git add tests/test_dungeon_integration.py
git commit -m "test: full-half dungeon engine integration"
```

---

## Task 11: Update the running log

**Files:**
- Modify: `log.md`

- [x] **Step 1: Append one entry**

Append (ASCII only): `2026-06-22 | Dungeon engine (Plan 1a): pure modules bands/power/score/items/loadout/treasury/dungeon/window_resolver + config blocks (bands,power,dungeon,economy) + item_templates.json; 15-min windows (window_seconds 900, windows_per_half 3, loadout_size 6). Full pytest coverage incl. full-half integration. No pygame. | config/game_config.json assets/data/item_templates.json src/game/{bands,power,score,items,loadout,treasury,dungeon,window_resolver}.py tests/test_*.py`

- [x] **Step 2: Commit**

```bash
git add log.md
git commit -m "docs: log dungeon engine (Plan 1a)"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage (Plan 1a slice = spec sections 4,5,6,7,8,11,16):**
- §4 bands -> Task 2. §5 Power -> Task 3. §6 dungeon/gates/dice -> Task 8 + resolver Task 9.
  §7 economy -> Task 7. §8 items + catalog-from-lineup -> Task 5; loadout -> Task 6.
  §11 party-size scaling -> Task 4 totals + Task 10 assertion. §3 window timing -> Task 1.
  §16 module map -> all tasks. (§9 relay, §10 log UI panel, §12-15 UI/resume/sim-UI/highscore
  are Plans 1b/2/3 — intentionally out of scope here; the crawl-log *strings* are produced by the
  resolver in Task 9 so the UI can render them later.)

**2. Placeholder scan:** none — every code step shows complete code; every run step shows the exact
command and expected result.

**3. Type consistency:** `DungeonState`, `GateOutcome`, `Item`, `Loadout`, `PartyGear`,
`WindowResult` and the functions `grade_progress/window_color/power_gain/total_tiles_half/
percent_complete/build_item/build_catalog/resolve_gate/resolve_window` use identical signatures
across the tasks that define and consume them. `score.total_tiles_half` is defined in Task 4 and
imported by `dungeon` (Task 8) — order is correct. The injected `rng` exposes `randint(a, b)` in
every call site (real `random.Random` satisfies this; tests use `SeqRng`).
