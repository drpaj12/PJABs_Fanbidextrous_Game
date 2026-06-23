# Dungeon Polish (Plan 3) Implementation Plan

> **For agentic workers:** Execute with superpowers:subagent-driven-development (fresh implementer subagent per task, two-stage review on the crux tasks). Steps use `- [ ]` checkboxes.

**Goal:** Polish the dungeon-crawl experience: reorder the launcher, rebalance the economy with loadout composition rules, restore per-prediction underline/colors from the simple game, mix prediction outcomes into the crawl log, add an end-of-half party recap, fix the overlapping shop UI with a draft-style zoom/buy panel, and add per-window monster flavor text.

**Architecture:** Pure game-logic changes (`src/game/`, tested in `tests/`) stay free of pygame; all rendering stays in `src/ui/`; all numbers stay in `config/`. The leader-authoritative party model is unchanged — followers still only read `view()`.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), pygame-ce, pytest. ASCII-only in print/log/.md.

---

## Decisions locked with the user (2026-06-23)

1. **Launcher:** keep existing labels; reorder so the *live* modes are on top and the *simulated* modes sink to the bottom. No rename.
2. **Economy:** weapons/armor/magic become premium; consumables cheap enough that a player can fill all six loadout slots with consumables inside a 300 pot. Composition rules: at most one weapon (already enforced via `two_handed`), armor and consumables allowed in multiples, but **no two armor of the same slot** ("can't have two helmets").
3. **Catch-up:** keep the existing static-default fill for missing/late picks. NO party-average catch-up. (No code change; documented only.)
4. **Consumables-per-window:** already implemented (`persist:"round"`); no change.

---

## File map

- `config/game_config.json` — launcher order is built in code, not config; add `dungeon.monsters` flavor block; (no economy numbers here — they live in item_templates).
- `assets/data/item_templates.json` — reprice; add armor `slots` list.
- `src/game/items.py` — add `armor_slot` field to `Item`; assign deterministically for armor.
- `src/game/loadout.py` — add no-duplicate-armor-slot rule to `can_add`.
- `src/game/window_resolver.py` — preserve per-stat outcomes + actuals on `WindowResult`; emit per-stat log lines.
- `src/game/dungeon.py` — add `monster_flavor(half, party_size, threat)` pure helper.
- `src/ui/screens/shop_screen.py` — draft-style card rows + zoom/buy detail panel.
- `src/ui/widgets.py` — add `ItemDetail` panel (mirrors `PlayerDetail`); teach `LogList` to color per-outcome lines.
- `src/ui/screens/dungeon_play_screen.py` and `src/ui/screens/party_play_screen.py` — per-prediction underline/colors after resolve; monster flavor in predict phase.
- `src/ui/screens/status_screens.py` — new `DungeonHalfScreen` recap.
- `src/ui/flow.py` — show `DungeonHalfScreen` between halves (SIM + party flows); reorder launcher options.
- `tests/` — new/updated tests for items, loadout, window_resolver, dungeon flavor.

---

### Task 1: Reorder the launcher (live on top, sims at the bottom)

**Files:**
- Modify: `src/ui/flow.py` (the `options = [...]` list in `start_launcher`, ~line 1096)

- [x] **Step 1:** Reorder the `options` list so live modes lead and simulated modes trail. Keep all existing labels and callbacks. Target order:
  1. `(_LAUNCHER["party_live_label"], go_party_live)`  — Dungeon party (live match)
  2. `(_LAUNCHER["live_label"], go_live)`              — Live match
  3. `(_LAUNCHER["party_label"], go_party)`            — Dungeon party (online, sim feed)
  4. `(_LAUNCHER["dungeon_label"], go_dungeon)`        — Dungeon crawl (simulated)
  5. `(_LAUNCHER["sim_label"], go_sim)`                — Test game (simulated)
- [x] **Step 2:** Verify headless: construct `LauncherScreen(App(), options)` under `SDL_VIDEODRIVER=dummy` and assert the first button label == `_LAUNCHER["party_live_label"]`.
- [x] **Step 3:** `.venv/Scripts/python -m pytest tests/ -q` (no regressions), confirm `.venv/Scripts/python src/main.py --party` still launches.
- [x] **Step 4:** Append to `log.md`; commit.

---

### Task 2: Economy rebalance + armor-slot rule

**Files:**
- Modify: `assets/data/item_templates.json`
- Modify: `src/game/items.py` (add `armor_slot` to `Item`, assign for armor)
- Modify: `src/game/loadout.py` (`can_add`: forbid duplicate armor slot)
- Test: `tests/test_loadout.py`, `tests/test_items.py` (create if missing)

- [x] **Step 1 (prices):** In `item_templates.json` set premium gear + cheap consumables:
  - weapon: `{"base": 150, "per_star": 30}`  (TUNED from 45 -> 30 during impl so the top 5-star weapon caps at 300, keeping one weapon affordable in a single fighter's pot; otherwise a 4-5 star weapon exceeded 300 and `test_buy_deducts_gold_and_adds_to_loadout` failed)
  - armor: `{"base": 110, "per_star": 30}`
  - consumable: `{"base": 35, "per_star": 5}`  (1-star=40 ... 5-star=55; six 1-stars = 240, comfortably under 300)
  - magic: `{"base": 160, "per_star": 50}`
  Add an armor `"slots": ["head", "body", "shield", "cloak"]` list aligned 1:1 with the four armor `names` entries.
- [x] **Step 2 (item field):** In `src/game/items.py` add `armor_slot: str = ""` to the `Item` dataclass. In `build_item`, when `category == "armor"`, set `armor_slot` to the slot whose index matches the chosen name index (reuse the existing `_stable_index("name:"+id, len(names))` so name and slot stay paired). Non-armor items keep `armor_slot=""`.
- [x] **Step 3 (failing test):** In `tests/test_loadout.py` add a test: build two armor `Item`s with the same `armor_slot` (different `item_id`); `can_add` the second returns `(False, "armor slot already filled")`. Also assert two armor of *different* slots both add, and that 6 cheap consumables all add (slot cap respected). Run it, expect FAIL.
- [x] **Step 4 (rule):** In `loadout.py` `can_add`, after the two-handed weapon check, add: if `item.category == "armor"` and any existing item has the same non-empty `armor_slot`, return `(False, "armor slot already filled")`.
- [x] **Step 5:** Run the new tests + full suite; expect PASS. Confirm the 1.5x second-half multiplier still applies on top of the new bases (existing test or add one: a half-2 catalog item price == round(base*1.5)).
- [x] **Step 6:** Headless: build a `CrawlSession(party_size=1)` with a synthetic 6-athlete pool, buy six consumables within the 300 pot, assert all six placed and treasury >= 0.
- [x] **Step 7:** `log.md`; commit.

**Two-stage review (crux):** spec compliance, then code quality.

---

### Task 3: Shop draft-style zoom/buy UI

**Files:**
- Modify: `src/ui/widgets.py` (add `ItemDetail` panel; mirror `PlayerDetail` at widgets.py:217-261)
- Modify: `src/ui/screens/shop_screen.py` (replace overlapping single-row buy with card rows + tap-to-zoom)
- Verify: headless construct smoke (no pytest — pygame UI)

- [x] **Step 1:** Add `ItemDetail` to `widgets.py`: constructor `(rect)` with a bottom `Button` (label set by caller to "Buy"/"Sell"). `draw(surface, item, treasury)` shows the category icon (`load_icon(item.category)`), item name, a line `f"{item.category}  {'*'*item.stars}  {item.price}g"`, the armor slot when present (`item.armor_slot`), the effect summary, and the player's current gold. Reuse `wrap_text` for the effect line.
- [x] **Step 2:** In `shop_screen.py` replace `_draw_row` content with a compact card: icon (left) + `item.name` + a short subtitle (`category + stars`), and an OWNED tint — NO right-aligned "tap to buy"/"OWNED" text (that overlap is the bug). Keep the existing scroll + viewport.
- [x] **Step 3:** Add zoom state mirroring `draft_screen.py` (`zoom_idx`): tapping a row sets `zoom_idx`; while zoomed, draw `ItemDetail` over the list with the button labelled "Buy" (if not owned) or "Sell" (if owned); tapping the button calls the existing buy/sell path; any other tap closes the zoom. Preserve the SIM auto-buy hotkey.
- [x] **Step 4:** Headless construct smoke: instantiate `ShopScreen` with a CrawlSession catalog, drive a tap on a row -> zoom open, tap Buy -> item bought (treasury decremented), draw both phases without traceback. Confirm no text is drawn in the row's right gutter (the old overlap region).
- [x] **Step 5:** `.venv/Scripts/python -m pytest tests/ -q`; confirm `src/main.py --dungeon` launches and the shop renders.
- [x] **Step 6:** `log.md`; commit.

**Two-stage review (crux):** spec compliance, then code quality.

---

### Task 4: Per-window prediction outcomes in the resolver + mixed log lines

**Files:**
- Modify: `src/game/window_resolver.py` (`WindowResult` + `resolve_window`)
- Test: `tests/test_window_resolver.py`

- [x] **Step 1 (failing test):** Add a test asserting `WindowResult` now carries `stat_results: list` where each entry is a small immutable record `(code, label, predicted, actual, band_label, color_key)` for the FIRST fighter's lines, and `actuals: dict` (the per-stat actual values used). Assert an exact prediction yields `color_key == "green"`, a big miss `"red"`, in-between `"orange"`. Run, expect FAIL.
- [x] **Step 2 (implement):** In `resolve_window`, while grading the first fighter's lines with `grade_progress(line, actual)`, build `stat_results` using the band: `green` if `band.key in ("exact","close")`, `red` if `band.is_big_miss`, else `orange`. Add `stat_results` and `actuals` fields to the `WindowResult` dataclass (defaults `field(default_factory=...)`). Keep tiles/color/gold math unchanged.
- [x] **Step 3 (mixed log):** After the existing `"... party advance +N (COLOR)"` line, append one per-stat line per stat, prefixed so the UI can color it, e.g. `f"PRED   {label} {predicted} vs {actual}  {band.label}"`. Keep these grouped under the window so the bottom log reads as: advance, per-prediction outcomes, POWER/GATE/DEPTH progression.
- [x] **Step 4:** Run tests + full suite; expect PASS. Confirm `stat_results` length == number of stats and order matches `STAT_CODES`.
- [x] **Step 5:** `log.md`; commit.

**Two-stage review (crux):** spec compliance, then code quality.

---

### Task 5: Prediction underline/colors + mixed log in the play screens

**Files:**
- Modify: `src/ui/widgets.py` (`LogList.draw` color rule)
- Modify: `src/ui/screens/dungeon_play_screen.py`
- Modify: `src/ui/screens/party_play_screen.py`
- Verify: headless construct smoke

- [x] **Step 1 (log colors):** In `LogList.draw`, color lines by prefix: `PRED ... GREEN`-> green text, `PRED ... RED`/`BIG MISS` -> red, `GATE ... FAIL` -> red, `POWER`/`GATE ... PASS` -> accent, else default. Keep the existing "GOAL" accent rule. (Simple `startswith`/`in` checks; no parsing of numbers.)
- [x] **Step 2 (dungeon underline/colors):** In `dungeon_play_screen.py` resolved phase, draw each of the 5 stat rows again as a compact results strip: `f"{label}: you {predicted} / was {actual}"` colored green/red/orange from `self.result.stat_results`, with an UNDERLINE (a `pygame.draw.line` under the text in the same color) for correct (green) predictions — mirroring the simple game's per-prediction feedback. Keep the depth meter + window-color cells below.
- [x] **Step 3 (party underline/colors):** Do the same in `party_play_screen.py` using `self.result`/the resolved data the screen already holds (the LOCAL player's lines vs `result.actuals`). Followers without a `result` fall back to the existing view-only rendering (no crash). DEVIATION: the party screen never holds a `WindowResult` (the leader resolves; followers read `view()`). Implemented by having the leader push per-window `actuals` into the canonical blob and grading the LOCAL player's `self.lines` against `view()["actuals"]` via the shared pure `window_resolver.build_stat_results`; clients without pushed actuals fall back to the depth/colors view.
- [x] **Step 4:** Headless smoke for both screens: resolve a window, switch to resolved phase, assert the strip draws colored lines + an underline rect for a green stat, no traceback.
- [x] **Step 5:** `.venv/Scripts/python -m pytest tests/ -q`; confirm `--dungeon` and `--party` launch.
- [x] **Step 6:** `log.md`; commit.

Also added the predict-phase `monster_flavor()` text render here (deferred from Task 4 / plan Task 7 logic step).

---

### Task 6: End-of-half party recap screen

**Files:**
- Modify: `src/ui/screens/status_screens.py` (new `DungeonHalfScreen`)
- Modify: `src/ui/flow.py` (show it between halves in `DungeonSimFlow._on_continue` and `DungeonPartyFlow._advance_then_shop`)
- Verify: headless construct smoke + party smokes

- [x] **Step 1:** Add `DungeonHalfScreen(app, percent, depth, total, members, log_tail, on_continue, title)` to `status_screens.py`. Render: title (e.g. `_HALFTIME_LABEL`), big `percent%`, `depth/total`, a per-player list `username — gold` (from `members` = list of (username, treasury)), and the last few crawl-log lines (`log_tail`). A Continue button -> `on_continue()`.
- [x] **Step 2 (SIM wiring):** In `DungeonSimFlow._on_continue`, when half 1 ends, show `DungeonHalfScreen` first; its Continue calls `begin_second_half()` + `_to_shop()`. Use single-device members `[(username, session.treasury)]`.
- [x] **Step 3 (party wiring):** In `DungeonPartyFlow._advance_then_shop`, after `leader_advance_half()`/`refresh()` build the screen from `coord.view()` (`percent`, `depth`, `total`, `members`, `log` tail). Continue calls `_reanchor_half_two()` + `_to_shop()`. Leader and follower both see it; only the leader advanced state. (DEVIATION: `_reanchor_half_two()` runs in `_advance_then_shop` before the recap is shown; the recap's Continue calls `_to_shop` directly — functionally equivalent ordering.)
- [x] **Step 4:** Headless construct smoke for `DungeonHalfScreen`. Re-run `TOOLS/smoke_party.py` and `TOOLS/smoke_party_live.py` — both must still print OK (the extra screen must not break the half transition; the smokes drive Continue).
- [x] **Step 5:** `.venv/Scripts/python -m pytest tests/ -q`; confirm `--dungeon` and `--party` launch and show the recap at halftime.
- [x] **Step 6:** `log.md`; commit.

**Two-stage review (crux):** spec compliance, then code quality (flow transition is the risk).

---

### Task 7: Per-window monster flavor text

**Files:**
- Modify: `config/game_config.json` (`dungeon.monsters` block)
- Modify: `src/game/dungeon.py` (pure `monster_flavor` helper)
- Modify: `src/ui/screens/dungeon_play_screen.py` and `src/ui/screens/party_play_screen.py` (show it in predict phase)
- Test: `tests/test_dungeon.py`

- [x] **Step 1 (config):** Add `"monsters": {"half1_name": "goblins", "half2_name": "ogres"}` under `dungeon`.
- [x] **Step 2 (failing test):** In `tests/test_dungeon.py` test `monster_flavor(half=1, party_size=3, threat=0)` returns a dict `{"total": T, "yours": Y, "name": "goblins", "text": "..."}` where `total == monster_difficulty(1, 3, 0)` and `yours == max(1, round(total / party_size))`, and `text` reads like `"Your party is engaging {total} {name}, you will fight {yours} of them."` Run, expect FAIL.
- [x] **Step 3 (helper):** Implement pure `monster_flavor(half, party_size, threat)` in `dungeon.py` using `monster_difficulty` for `total`, `name` from config by half, `yours = max(1, round(total / party_size))`, and the ASCII `text` string.
- [x] **Step 4 (UI):** In both play screens' predict phase, render `monster_flavor(...).text` (party uses `coord.half()`/party size; single-device uses the session). Wrap with `wrap_text` so it fits 414px. (Shipped within the Task 5 commit.)
- [x] **Step 5:** Run tests + full suite; confirm `--dungeon`/`--party` show the flavor line in the predict phase.
- [x] **Step 6:** `log.md`; commit.

---

## Amendments (2026-06-23, round 2 — approved)

The user approved the plan and added four refinements. Tasks 3/4/5 absorb the first two; Tasks 8 and 9 are new.

- **Draft-style prediction detail (folds into Tasks 3 & 5):** the window prediction stat rows should be presented with the same polished card/detail treatment as the draft screen — not cramped dial text. The resolved-phase per-prediction results ("you X / was Y", green/orange/red, underline for correct) are the detail payload.
- **Bottom log = flavor + colored guess results (folds into Tasks 4 & 5):** the crawl log must interleave the monster flavor text (Task 7) AND each prediction's actual result, color-coded green (exact/close), orange (near/mid), red (miss/big miss). The monster flavor line is appended to `result.log` at resolve time so it scrolls in the same log.

### Task 8: Live wall clock + actual game score on the play screens

**Files:**
- Modify: `src/ui/widgets.py` (small reusable `draw_match_banner` helper, or inline)
- Modify: `src/ui/screens/dungeon_play_screen.py`, `src/ui/screens/party_play_screen.py`
- Modify: `config/game_config.json` only if a label is needed

- [x] **Step 1:** Add a top banner on both play screens showing: the actual match scoreline `HOME g - g AWAY`, the match minute/status, and the real wall-clock time of day (HH:MM). Dungeon (single-device) reads score/minute from its `feed`/session match meta (the existing `_match_line` already derives home/away/goals/minute — extend it). Party reads from `coord.view()["match"]` (home, away, home_goals, away_goals, minute, status).
- [x] **Step 2:** Wall clock: use `time.strftime("%H:%M")` (pygbag-safe; NOT `Date.now()`-style). Place it in the banner. In sim modes where there is no real match, still show the simulated minute + score; the wall clock is real time of day either way.
- [x] **Step 3:** Headless construct smoke: both screens draw the banner with a stub match dict, no traceback, score + minute + a HH:MM clock string present.
- [x] **Step 4:** `pytest`; confirm `--dungeon`/`--party` show the banner. `log.md`; commit.

### Task 9: Game picker in ALL modes

**Files:**
- Create: `src/ui/screens/sim_game_select_screen.py` (lists recorded simulations)
- Modify: `src/ui/flow.py` (route every dungeon mode through a picker before play)
- Modify: `config/game_config.json` (`launcher.simulations_dir` or reuse `assets.data_dir`)

- [x] **Step 1:** Build `SimGameSelectScreen(app, games, on_pick)` listing the recorded simulations in `assets/data/simulations/` (currently `wc2018_final_fra_cro`, `wc2018_qf_bra_bel`, `wc2018_sf_fra_bel`). Each row shows a readable label (derive from filename or a `meta` block in the JSON: home v away). `on_pick(path)` starts that game. Reuse the row/scroll pattern; tap a row to select. (Discovery is a pure `src/game/simulations.py::list_simulations(root, dir) -> [SimGame]`; the screen renders title + subtitle.)
- [x] **Step 2 (sim modes):** Route the simulated dungeon (`go_dungeon` / `start_dungeon`) and the online/sim party (`go_party`) through `SimGameSelectScreen` first; the picked simulation file feeds the existing flow (replaces the hardcoded `launcher.test_sim` default). Done via new `start_sim_select(app, on_pick, sim_mode)`; the simple test game (`go_sim`) routes through it too, and CLI `--dungeon`/`--party` as well, so EVERY offline mode begins with a game list.
- [x] **Step 3 (live modes):** Verify the live single-player and live party modes already route through `fixture_select_screen.py`. (Confirmed: `start_live_select` and `start_dungeon_party_live` both open `FixtureSelectScreen`; no live path skips the picker.)
- [x] **Step 4:** Headless construct smoke for `SimGameSelectScreen` (3 rows, tap fires `on_pick` with the right path; SIM auto-picks first; empty state safe). `TOOLS/smoke_party.py` + `smoke_party_live.py` still print OK (drive the coordinator directly, not the launcher, so the picker does not affect them).
- [x] **Step 5:** `pytest` 311 pass (307 + 4 new); `--dungeon`/`--party`/`--launcher` launch and land on a game list / launcher. `log.md`; commit.

**Two-stage review (crux):** spec then code quality (flow routing touches every entry point).

## Final review

After all tasks: dispatch a whole-implementation reviewer (leader/follower convergence intact, no pygame in `src/game`, no magic numbers, ASCII-only, all tests green, both party smokes OK). Then rebuild the deploy (`build_web_mobile.py --build-only` + mirror + `package_deploy.py`) only when the user asks to ship.

## Self-review notes
- Spec coverage: launcher(1), economy+armor-slot(2), shop overlap fix(3), per-prediction outcomes(4)+underline/colors(5), mixed log(4 emits / 5 colors), end-half recap(6), monster flavor(7), scaling answered in chat, catch-up unchanged per decision. All covered.
- Type consistency: `armor_slot` field name used in items.py, loadout.py, ItemDetail; `stat_results`/`actuals` field names used in resolver + both play screens; `monster_flavor` signature `(half, party_size, threat)` consistent.
