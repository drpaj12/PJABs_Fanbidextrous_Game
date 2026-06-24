# Peer-Computed Co-op Crawl Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Execute task-by-task: write test, run it red, implement, run it green, commit.

**Goal:** Replace the interim leader-authoritative co-op transport with a peer-computed model where every client resolves the dungeon locally from shared inputs (creator-set seed + lead-shared per-window input bundle), so no client ever hangs waiting on another player.

**Architecture:** The party relay becomes a bulletin board of INPUTS, not authoritative dungeon OUTPUT. The creator writes a single random `seed` into the blob once. The api-lead (creator) polls the match feed and, for each window it resolves, shares a frozen per-window input bundle `{actuals, lines, use}` into `window_actuals[str(window)]`. Every client (lead + followers) runs the SAME deterministic `CrawlSession.resolve_window` over that bundle with the shared seed, producing byte-identical dungeon state locally. Followers never wait for a leader push and never wait for other players' picks. `resolve_window` is unchanged; this is purely a new coordinator + relay-field + flow-wiring layer.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), pygame-ce/pygbag (UI only), PHP relay (`soccer_api.php`), pytest. Golden rule: `src/game/` + `src/sync/` import zero pygame.

---

## Why peer-compute removes the hang

The interim co-op reuses the leader-authoritative `PartyCoordinator`, whose hangs are:
1. `leader_try_reconcile_shop` blocks until ALL members `ready` (no timeout).
2. SIM resolution `require_all=True` blocks until ALL picks are in.
3. Followers render only the leader's pushed `dungeon`, so a dark/slow leader freezes them.

The peer model removes all three: (1) each client proceeds to play on its own clock the moment it has shopped; (2) resolution uses a frozen input bundle with `DEFAULT_LINES` for any missing pick (`require_all=False` always); (3) each client computes its own dungeon — the relay carries inputs, not output. The only remaining dependency is on the api-lead for match data (the locked design: "only lead polls API"), which is inherent and accepted for v1.

## Determinism guarantee

Byte-identical local results require every client resolve window W with the SAME inputs. We guarantee this by FREEZING inputs at the lead: when the api-lead resolves W it captures `{actuals, fighter_lines, used}` and shares that exact bundle in `window_actuals[str(W)]`. Followers resolve W by replaying the bundle (not by reading the live, mutable `window_picks`, which is keyed per-slot-latest and would otherwise drift to W+1). Same seed (creator-set) + same bundle + same `party_size` (frozen at shop start) => identical `CrawlSession` state. Documented v1 assumption: party_size is frozen when the creator pushes members at shop start; late joiners after start are not added mid-game.

## File Structure

- **Create** `src/sync/peer_coordinator.py` — `PeerCoordinator(PartyCoordinator)`. Every client `is_leader=True` (so the flow/screen resolution path fires locally on all clients); separate `is_api_lead` for who polls the API + writes seed/bundles/members. Overrides: `join`, `refresh`, `leader_start`, `leader_try_reconcile_shop`, `leader_try_resolve`, `leader_advance_half`, `resolved_through`, `view`, `_push_after_resolve`. Adds `polls_api` property + `_resolution_input(window)`.
- **Modify** `src/game/party.py` — add `seed: Optional[int]` and `window_actuals: dict` to `Party` (+ to_dict/from_dict). Add `polls_api`-irrelevant helper `peer_bundle(party, window)` if useful.
- **Modify** `php/soccer_api.php` + mirror `PHP_SCRIPTS/soccer_api.php` — `seed`/`window_actuals` in `create_empty_party` blob and `action_party_push` allowed-key list.
- **Modify** `src/sync/party_coordinator.py` — add `polls_api` property (= `is_leader`) so the flow can gate API polling generically without breaking the existing leader-authoritative path.
- **Modify** `src/ui/flow.py` — `leader_poll_feed` guard `is_leader`->`polls_api`; `_windows_elapsed`/`_live_data_ready` peer-aware (follower reads blob `window_actuals`); `start_dungeon_party_live(..., peer=False)` builds `PeerCoordinator` + sets `flow.peer`/`flow.is_api_lead` when `peer=True`; launcher `go_party_coop` passes `peer=True`.
- **Modify** `tests/` — `test_party.py` (field round-trip), new `tests/test_peer_coordinator.py` (two-client determinism, no-barrier, defaults, half advance).

---

### Task 1: party.py seed + window_actuals fields

**Files:**
- Modify: `src/game/party.py` (Party dataclass + to_dict/from_dict)
- Test: `tests/test_party.py`

- [ ] Step 1: Add a failing test asserting `Party(...).seed` / `window_actuals` survive a `to_dict`/`from_dict` round-trip and default to `None`/`{}`.
- [ ] Step 2: Run it red.
- [ ] Step 3: Add `seed: Optional[int] = None` and `window_actuals: dict = field(default_factory=dict)` to `Party`; include both in `to_dict` (`window_actuals` as a dict copy) and `from_dict` (`seed` coerced to int-or-None, `window_actuals` via a small `_actuals_dict` coercer that keeps only well-formed entries, mirroring `_picks_dict`).
- [ ] Step 4: Run tests green.
- [ ] Step 5: Commit.

### Task 2: PeerCoordinator core + determinism test

**Files:**
- Create: `src/sync/peer_coordinator.py`
- Test: `tests/test_peer_coordinator.py`

Key behaviors (full code written during execution):
- `join`: super().join() sets is_api_lead from relay `is_leader`; force `self.is_leader=True`; if api-lead push `seed` (+ empty `window_actuals`); else adopt blob `seed`.
- `refresh`: super, then adopt `seed` from blob when present.
- `polls_api` property = `is_api_lead`.
- `leader_start`: api-lead only — push `{phase:shop, members(treasury=_PER_PLAYER, ready=False), seed, window_actuals:{}}`.
- `leader_try_reconcile_shop`: no barrier — refresh, `_build_session`, re-apply all members' loadouts, return True (push nothing).
- `_resolution_input(window)`: api-lead computes `{actuals: actuals_fn(w), lines: fighter_lines_from_picks, use: used_consumables_from_picks}`; follower reads `party.window_actuals[str(w)]` (coerced) or None.
- `leader_try_resolve(window, require_all=False)`: skip if `window <= self._resolved_through`; bundle = `_resolution_input`; None => False; re-apply loadouts; `session.resolve_window(lines, actuals, label, used)`; set `_resolved_through`; api-lead `_push_after_resolve(window, bundle)`.
- `_push_after_resolve`: api-lead only — members treasury/wounds/items (reuse parent share logic), dungeon payload, log, window_colors, `resolved_through_window`, merged `window_actuals` (NO clear_picks).
- `leader_advance_half`: local `begin_second_half` + reset `_resolved_through=0` for everyone; api-lead pushes `{phase:shop, half:2, members topped, clear_picks:True, window_actuals:{}}` (H1) or `{phase:done}` (H2).
- `resolved_through`: returns local `_resolved_through`.
- `view`: build from local `self.session.state` (depth/power/wounds/threat/log/window_colors/percent via `cleared_total`); members + match from blob; total from `total_tiles_game`.

- [ ] Step 1: Test — two `PeerCoordinator`s (creator + follower) over ONE shared `LocalRelay`, same actuals_fn, both submit loadouts + picks, both resolve windows 1..3; assert identical `view()` depth/wounds/log/window_colors/percent and identical `session.state.to_dict()`.
- [ ] Step 2: Run it red (module missing).
- [ ] Step 3: Implement `PeerCoordinator`.
- [ ] Step 4: Run green.
- [ ] Step 5: Add tests: follower resolves from shared bundle even when its own pick for W never arrived (defaults, still matches lead); no reconcile barrier (reconcile returns True with a member not ready); half advance resets local resolved + clears window_actuals.
- [ ] Step 6: Run green; commit.

### Task 3: soccer_api.php seed + window_actuals

**Files:**
- Modify: `php/soccer_api.php`; mirror to `PHP_SCRIPTS/soccer_api.php` (deploy copy)

- [ ] Step 1: Add `'seed' => 0` (or null-equivalent) and `'window_actuals' => new stdClass()` to `create_empty_party`.
- [ ] Step 2: Add `'seed'` and `'window_actuals'` to the `action_party_push` allowed-key foreach list.
- [ ] Step 3: `php -l` lint both files (if php available) or visual diff; mirror identical change into the deploy copy.
- [ ] Step 4: Commit.

### Task 4: party_coordinator polls_api + flow wiring

**Files:**
- Modify: `src/sync/party_coordinator.py` (add `polls_api` property)
- Modify: `src/ui/flow.py`

- [ ] Step 1: Add `@property polls_api(self) -> bool: return self.is_leader` to `PartyCoordinator`.
- [ ] Step 2: `flow.leader_poll_feed`: change guard `not self.coord.is_leader` -> `not self.coord.polls_api`.
- [ ] Step 3: `DungeonPartyFlow.__init__`: add `self.peer = False`, `self.is_api_lead = False`.
- [ ] Step 4: `_windows_elapsed`: when `self.peer and not self.is_api_lead`, return count of current-half windows present in `coord.party.window_actuals`. Else existing feed-based.
- [ ] Step 5: `_live_data_ready(window)`: when `self.peer and not self.is_api_lead`, return `str(window) in coord.party.window_actuals`. Else existing.
- [ ] Step 6: `start_dungeon_party_live(..., peer=False)`: when `peer`, build `PeerCoordinator` in BOTH lead and follower branches and set `flow.peer=True`, `flow.is_api_lead=is_lead`.
- [ ] Step 7: launcher `go_party_coop` -> `start_dungeon_party_live(..., solo=False, peer=True)`.
- [ ] Step 8: Run full pytest; verify launch headless. Commit.

### Task 5: Build, deploy, log

**Files:** TOOLS build scripts, WEB_BUILD mirror, log.md

- [ ] Step 1: `.venv/Scripts/python -m pytest tests/` all green.
- [ ] Step 2: Smoke (`TOOLS/smoke_party.py`, `smoke_party_live.py`) green.
- [ ] Step 3: Build mobile + desktop web; mirror into `WEB_BUILD/PREDICTOR`; package `PREDICTOR_deploy.zip` with updated PHP.
- [ ] Step 4: Append one line to `log.md`.
- [ ] Step 5: Commit to main and push.

## Self-Review notes

- Type consistency: `window_actuals` is `dict[str, dict]` everywhere; bundle keys `actuals`/`lines`/`use` consistent across coordinator + tests.
- Spec coverage: seed (creator-set, blob), window_actuals (lead-shared bundle), peer coordinator (local resolve), PHP fields, flow gating, build/deploy — all have tasks.
- v1 documented assumptions: only api-lead polls API + writes bundles; party_size frozen at shop start; picks-divergence eliminated by frozen bundle replay.
