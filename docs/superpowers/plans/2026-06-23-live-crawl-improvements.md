# Live Crawl Improvements Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Golden rule: `src/game/` stays pygame-free and unit-tested; `src/ui/` holds all rendering; all tunables in `config/*.json`. Always run `.venv/Scripts/python -m pytest tests/` and a launch smoke after each task; append to `log.md`.

**Goal:** Fix live-crawl window gating and add three crawl features (picks-in confirmation, leftover-monster scaling, per-window potion choice), per the 2026-06-23 design Q&A.

**Architecture:** Pure game logic (catch-up planning, monster carry-over) lives in `src/game/` with tests; the play/predict screens in `src/ui/` consume it. The leader-authoritative party model is unchanged -- the leader still owns the `CrawlSession`.

**Tech Stack:** Python 3.11, pygame-ce, pytest. Run via `.venv/Scripts/python`.

---

## Design decisions (from user Q&A 2026-06-23)

1. **Live gating / catch-up:** Auto fast-forward. On entry mid/post-match, windows already played auto-resolve using the player's locked pick (or defaults), landing the player on the CURRENT live window, gated there until real data arrives. The player's shop purchases (loadout) still apply during catch-up. If catch-up crosses into the 2nd half, the 2nd-half per-player treasury (300g) is granted automatically (no manual shop mid-catch-up).
2. **Picks-in display:** After submit, show a "Windows" panel listing each window's picks (`W1: G 1  S 2 ...`), underlining the window currently being resolved. Bring back the previous game's red/orange/green per-stat "locked in" scheme in the predict phase (red = untouched, orange = adjusted-not-locked, green = locked = the bet).
3. **Monster scaling / carry-over:** Each window engages monsters scaled to ACTUAL party size (solo = 1xN, full party = 3xN -- not the current base+per-extra-fighter formula). Tiles advanced kill that many monsters; unkilled monsters carry over as added threat to the party next window.
4. **Potions:** Potions bought in the shop persist in inventory until used. A per-window "USE" toggle on the predict screen (a zoom-in item card with a USE button, mirroring the earlier player-buff picker) deploys one this window; consumed only when used.

---

## Increment A: Live catch-up + edge gating

**Files:**
- Create: `src/game/live_catchup.py` (pure: plan which past windows to auto-resolve given match minute + clock)
- Create: `tests/test_live_catchup.py`
- Modify: `src/ui/flow.py` (DungeonPartyFlow: drive auto-resolve of elapsed windows on entry / after each resolve; grant H2 treasury automatically during catch-up)
- Modify: `src/ui/screens/party_play_screen.py` (clear "waiting for the match to reach this window" gated state instead of generic "Waiting...")

**Mechanics:**
- A pure helper `windows_elapsed(match_minute, clock, windows_per_half, half) -> int` returns how many windows of the current half the match has fully played (feed-covered). The flow uses it to know which windows are "caught up" (auto-resolve) vs the live edge (gate).
- Catch-up auto-resolves each elapsed window with the player's submitted pick if present, else the default lines, applying the current loadout. It must reuse the existing leader resolution path (`leader_try_resolve` with `require_all=False`) so followers stay consistent.
- On reaching the live edge, the screen stays in a gated "wait" state showing e.g. `Locked. Waiting for the match to reach 45'...` and never shows an enabled Continue for a not-yet-played window.
- If catch-up advances past the H1->H2 boundary, call the existing half-advance path and auto-grant the per-player treasury (`party.per_player_treasury`) without opening the shop; carry the existing loadout into H2.

**Tasks:**
- [x] A1: Write failing tests for `windows_elapsed` (mid-H1, exact boundary, past-H1-into-H2, finished match) in `tests/test_live_catchup.py`.
- [x] A2: Implement `src/game/live_catchup.py::windows_elapsed`; tests pass.
- [x] A3: Wire DungeonPartyFlow to auto-resolve elapsed windows on entry and land on the live edge (leader path; followers via existing poll/refresh). Implemented via `PartyCoordinator.leader_catch_up` + async `_enter_live_window`.
- [x] A4: Auto-grant H2 treasury during catch-up across the half boundary; carry loadout. `leader_advance_half` tops each pot up to `per_player_treasury` (300g).
- [x] A5: Add the gated "waiting for the match" state to PartyPlayScreen ("Picks in. Waiting for the match..." when `can_resolve` gates; no Continue past the live edge).
- [x] A6: pytest (326 pass) + `--party` smoke OK; appended log.md.

## Increment B: Picks-in confirmation + red/orange/green lock

**Files:**
- Modify: `src/ui/screens/party_play_screen.py` (per-stat lock state; tri-color dials; windows panel with resolving-window underline; "Picks in" header in wait phase)
- Modify: `src/sync/party_coordinator.py` if needed to expose this player's per-window submitted picks for the panel (read-only `view()` addition)
- Modify: `config/layout_config.json` (panel/dial layout keys as needed)

**Mechanics:**
- Predict phase: each stat dial shows a red (untouched) / orange (adjusted, not locked) / green (locked) indicator, tapped to lock, mirroring `live_play_screen._draw_stats`. The "bet" = locked (green) stats.
- Wait phase: replace generic "Waiting..." with a "Picks in" header plus a Windows panel (`W1: G 1  S 2 ...`), newest-first, with the window currently being resolved underlined (mirrors `live_play_screen._draw_locked_panel`).

**Tasks:**
- [x] B1: Add per-stat lock state + tri-color dials to the predict phase. (locked/touched sets; body-tap toggles lock; +/- arms orange; green=locked dot + accent border.)
- [x] B2: Add the "Picks in" + Windows panel to the wait phase, underlining the resolving window. (pick_history threaded from the flow so it survives per-window screen rebuilds.)
- [x] B3: Layout keys (pplay_lock_circle_r, pplay_panel_*); no magic numbers.
- [x] B4: pytest (326) + headless render check + `--party` smoke; append log.md.

## Increment C: Monster scaling + leftover carry-over

**Files:**
- Modify: `src/game/dungeon.py` (`monster_difficulty` / `monster_flavor` scale to party_size; new leftover computation)
- Modify: `src/game/window_resolver.py` (`resolve_window`: carry unkilled monsters into `state.threat`)
- Modify: `config/game_config.json` (dungeon: `monster_per_fighter_half1/2`; deprecate base+per-fighter if replaced)
- Modify: `tests/test_dungeon.py` and/or `tests/test_window_resolver.py`

**Mechanics:**
- Total monsters engaged this window = `monster_per_fighter[half] * party_size + threat` (solo = 1xN). Keep `monster_difficulty_per_threat` as the threat contribution.
- Tiles advanced this window kill up to that many monsters; leftover = `max(0, total - kills)`. Leftover is added to `state.threat` so the next window is harder ("the party gets allocated the ones left").
- `monster_flavor` text and `yours` share recomputed against the new total.
- Preserve existing gate pass/fail/wound semantics; the carry-over is additive to threat, replacing the flat `+1 on big miss` (or layered with it -- decide in C1 and document).

**Tasks:**
- [x] C1: Decided leftover STACKS with the +1 big-miss. Tests: monster_count scaling (solo 1xN, party 3xN, +threat), leftover->threat carry, overkill no-leftover, big-miss-stacks-with-carry.
- [x] C2: Implemented `monster_count`/`monster_name` in `dungeon.py`; `monster_flavor` repointed to `monster_count`; tests pass.
- [x] C3: Implemented leftover->threat carry-over in `resolve_window` (kills = min(engaged, tiles); leftover -> state.threat with HORDE log); tests pass.
- [x] C4: Added `monster_per_fighter_half1/2` config keys + `_monster_comment`; no magic numbers.
- [x] C5: pytest (330) + `--party` smoke OK (clean); appended log.md.

## Increment D: Per-window potion choice

**Files:**
- Modify: `src/game/crawl.py` (potions persist in inventory; consume only when used; `party_gear()` reads chosen potions)
- Modify: `src/game/window_resolver.py` if the consumable application path needs the "used this window" flag
- Modify: `src/ui/screens/party_play_screen.py` and/or a small detail widget (zoom-in item card + USE toggle, mirroring `draft_screen.PlayerDetail.select_btn`)
- Modify: `src/sync/party_coordinator.py` (carry the per-window "use potion" choice in the submitted pick payload)
- Modify: `tests/` for the inventory/consume logic

**Mechanics:**
- Consumables no longer auto-drop every window (`_drop_consumables` only removes a potion when actually used). They sit in inventory until the player toggles USE for a window.
- Predict phase: tapping a held potion opens a zoom-in card with a USE button that toggles deployment for this window. Only a toggled potion contributes `consumable_value` at the gate and is consumed on use.
- The pick payload submitted to the coordinator carries the potion choice so the leader's resolution applies it.

**Tasks:**
- [x] D1: Tests: potion persists unused, consumed only when used, party_gear counts only used (test_crawl); used_consumables_from_picks ordering (test_party); relay `use` payload (test_relay_client); coordinator consumes-on-use / persists-unused (test_party_coordinator).
- [x] D2: crawl.py: party_gear(used_consumables)/resolve_window(used_consumables)/_drop_consumables(used_consumables) -- consumables persist until USED, only deployed ones contribute value and drop.
- [x] D3: Pick payload carries `use` (relay_client.party_pick + PHP action_party_pick + coordinator.submit_pick); leader_try_resolve applies used_consumables_from_picks and strips spent potions from each member's pushed inventory.
- [x] D4: Predict-screen potion chips + zoom-in USE toggle (mirrors draft PlayerDetail); _sync_pool_from_blob aligns coord.pool so followers see their potions. New layout keys pplay_potion_*/pplay_zoom_*.
- [x] D5: pytest (337) + headless potion render/toggle/submit check + `--party` smoke OK; appended log.md.

---

## Suggested order
A (the reported bug) -> B (the visible picks-in confirmation) -> C (combat) -> D (potions). C and D both touch resolution/gear; B and D both touch the predict screen, so doing B before D keeps the predict-screen changes coherent.

## Open detail to confirm during build
- C1: RESOLVED -- leftover-as-threat STACKS with the flat `+1 threat on big miss` (both apply; a big miss that also leaves the horde unslain adds 1 + leftover).
- A: during catch-up across the half boundary, is the H2 loadout simply the H1 loadout carried forward (no auto-spend of the 300g), with the player free to re-shop once caught up? (Assumed yes unless told otherwise.)
