# Cooperative Dungeon-Crawl Redesign — Design

Status: APPROVED (brainstorm). Date: 2026-06-22.

Re-mechanics the live soccer predictor into a cooperative, leader-authoritative
**dungeon crawl** for a party of 1-3 fighters. The same prediction engine drives a new
progression layer: accuracy bands move the party deeper through a linear dungeon, a gold
economy replaces drafting with a shop of items derived from the real match lineup, and the
party's score becomes "percent of dungeon completed." The real match scoreline stays on
screen for flavour. Tested offline against recorded World Cups (sim mode) and live against
real fixtures via the PHP relay.

---

## 1. Goals / non-goals

**Goals**
- 15-minute prediction windows: 3 windows per half (w1 pre-kickoff, w2 @15', w3 @30'+stoppage), 5 stats each = 15 predictions per half.
- Accuracy bands (exact/close/near/off/big-miss) convert each window into tiles of dungeon depth.
- A correct (non-zero) goal prediction grants persistent **Power** for the rest of the crawl.
- Linear depth track with **monster gates** resolved by seeded dice + equipped items.
- **Gold economy + shop**: each fighter buys up to 6 items (paid from a shared party treasury); the 22-item catalog is generated from the current match's real lineup players.
- **Party of 1-3** via "Create Party"/"Join Party"; leader-authoritative JSON state file on the relay enables dropout/rejoin by username.
- Party-size scaling so 1- or 2-fighter parties stay balanced.
- Score = percent of dungeon completed; window cells colored green/orange/red; a scrollable crawl log; a depth meter at the bottom of the play screen.
- Hand-authored PNG icons for items, enemies, and dungeon tiles.
- Sim mode plays recorded old World Cups for deterministic mechanics testing.

**Non-goals**
- More than 3 fighters per party.
- Retaining the old success/concede -> shot -> goal scoring loop (retired; scoreline display kept).
- Native app; persistent Python backend (PHP relay remains the only server component).

---

## 2. Authority order for this redesign
1. This spec — intended mechanics.
2. `src/game/` modules — exact behavior (pure, zero pygame).
3. `the_idea.md` / `DESIGN.md` — original architecture and scope.

The golden rule still holds: `src/game/` is pure and testable; `src/ui/` holds all pygame;
`config/*.json` holds every constant; `tests/` test `src/game/` only.

---

## 3. Windows & timing

- `game.window_seconds`: 300 -> **900** (15 min). `game.half_minutes` stays 45 -> **3 windows/half**.
  - w1: pre-kickoff..15', w2: 15'..30', w3: 30'..45'+stoppage. w3 absorbs extra time exactly
    like today's final window (runs until the feed reports half/full time).
- "Edit one ahead" model is unchanged: lock w1 before kickoff, edit w2 during w1, w3 during w2.
- 5 stats/window unchanged in `stats_menu.json`: `goal` (power) + `shot`, `corner`, `card`, `foul` (4 progress).
- `game.windows_per_half = 3` added (derived check: `half_minutes*60 / window_seconds`).

The existing `half_clock.py` already computes windows from `window_seconds`/`half_minutes`
and treats the last window as the extra-time catch-all; changing the config values yields 3
windows with no clock-logic change. `_max_entered`, lock/resolve deferral, and the
edit-one-ahead invariant are preserved.

---

## 4. Accuracy bands (pure: `src/game/bands.py`)

Each of the 4 **progress** stats is graded into a band by absolute error, yielding
**step-points** (tiles). New config block `bands`:

```json
"bands": {
  "exact":    {"max_diff": 0, "step": 3, "label": "EXACT"},
  "close":    {"max_diff": 1, "step": 2, "label": "CLOSE"},
  "near":     {"max_diff": 2, "step": 1, "label": "NEAR"},
  "off":      {"max_diff": 4, "step": 0, "label": "OFF"},
  "big_miss": {"max_diff": 999, "step": -1, "label": "BIG MISS"}
}
```

- `grade_progress(line, actual) -> Band` returns the first band whose `max_diff` covers the error.
- A window's **tile advance** = sum of its 4 progress-stat steps (max +12 if all exact).
- A `big_miss` also raises one **threat** point (used to strengthen the next monster gate).

**Window color** (`window_color(window_result) -> str`), config `bands.window_color`:
- `green` if window tiles >= `green_min` (default 8),
- `red` if window tiles <= `red_max` (default 2) OR the window contains any big_miss,
- `orange` otherwise.

The goal stat is NOT graded here for tiles; see Power below.

---

## 5. Power — persistent goal-prediction modifier (pure: `src/game/power.py`)

The `goal` stat is the **power roll**, graded separately and granting Power that persists for
the whole crawl (stacks across windows and halves). Config block `power`:

```json
"power": {
  "exact_gain": 2,
  "close_gain": 1,
  "close_max_diff": 1,
  "min_predicted": 1,
  "roll_bonus_per_power": 1,
  "gold_bonus_per_power": 0.10
}
```

- `power_gain(predicted_line, actual) -> int`:
  - returns 0 if `predicted_line < min_predicted` (predicting 0 never grants Power),
  - `exact_gain` if error == 0,
  - `close_gain` if error <= `close_max_diff`,
  - else 0.
- Accumulated `power` adds `roll_bonus_per_power * power` to every monster-pass dice roll and
  multiplies gold gain by `(1 + gold_bonus_per_power * power)`.

---

## 6. Depth, monster gates, dice (pure: `src/game/dungeon.py`)

The dungeon is a **linear tile track**. New config block `dungeon`:

```json
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
}
```

- **Total tiles** for a half = `tiles_per_fighter_halfN * party_size` (party-size scaling, sec. 11).
  Trio H1 = 36 (3 windows x 12 max), so near-perfect play can complete a half.
- **Gates** sit at multiples of `gate_every_tiles_halfN`. When the party's advance crosses a gate,
  the leader resolves it before continuing past it.
- **Gate roll** (`resolve_gate(rng, party, threat) -> GateOutcome`):
  - `roll = rng.randint(1, dice_sides) + best_weapon_bonus(party) + roll_bonus_per_power*power`
  - `difficulty = monster_base_difficulty_halfN + monster_difficulty_per_fighter*(party_size-1) + monster_difficulty_per_threat*threat`
  - PASS if `roll >= difficulty`. Loot gold on pass (sec. 7).
  - FAIL: `shortfall = difficulty - roll`; `best_armor_soak(party)` reduces it; any leftover costs
    `tiles_lost_per_unsoaked_point` tiles and inflicts 1 wound. At `max_wounds` the crawl ends for
    that half (the party still keeps its depth %).
  - **Consumables** queued in the pick window are applied first (auto-pass or +roll). Magic rerolls
    apply on a fail before armor.
- All randomness uses the existing seeded RNG; **only the leader rolls** and writes results
  (sec. 9), so followers never re-roll and cannot diverge.

`DungeonState` (pure dataclass): `half`, `depth`, `total_tiles`, `power`, `wounds`, `threat`,
`next_gate_tile`, `gates_passed`, `finished`. Serializable for the party file and resume.

---

## 7. Gold & the two halves (pure: `src/game/treasury.py`)

New config block `economy`:

```json
"economy": {
  "base_treasury_per_fighter": 300,
  "gold_per_tile": 5,
  "gold_depth_bonus_per_gate": 3,
  "gate_loot": 50,
  "second_half_price_multiplier": 1.5
}
```

- **Shared party treasury.** Buying spends from it; any fighter can buy their own loadout.
- Gold awarded per tile advanced = `gold_per_tile + gold_depth_bonus_per_gate * gates_passed`,
  times the Power gold multiplier. Gate passes add `gate_loot`.
- **First half:** treasury starts at `base_treasury_per_fighter * party_size`.
- **Second half:** a re-buy/upgrade phase before a harder dungeon; item prices are multiplied by
  `second_half_price_multiplier`. The treasury carries over (minus first-half spend, plus crawl gold).

---

## 8. Items — catalog generated from the real lineup (pure: `src/game/items.py`)

The 22-item catalog is **built at match time from the 22 lineup athletes** (both teams' XI +
subs), so items always relate to who is actually playing. Mapping by `broad_position`:

| broad_position | Category   | Persist     | Role |
|----------------|------------|-------------|------|
| Attacker       | `weapon`   | infinite    | + dice bonus on monster rolls |
| Defender       | `armor`    | infinite    | soak failed-roll shortfall |
| Midfielder     | `consumable`| single round| one-shot: auto-pass / +roll / +tiles |
| Goalkeeper     | `magic`    | infinite    | +gold / reroll / +Power / +1 item slot |

Naming templates + pricing/effect formulas live in a new `assets/data/item_templates.json`
(NOT a fixed item list — the list is generated):

```json
{
  "weapon":     {"names": ["Sword of {sur}", "Blade of {sur}", "Spear of {sur}", "Axe of {sur}"],
                 "two_handed": true,
                 "price": {"base": 120, "per_star": 40},
                 "effect": {"kind": "dice_bonus", "base": 1, "per_star": 1}},
  "armor":      {"names": ["Aegis of {sur}", "Helm of {sur}", "Bulwark of {sur}", "Mail of {sur}"],
                 "price": {"base": 90, "per_star": 30},
                 "effect": {"kind": "soak", "base": 1, "per_star": 1}},
  "consumable": {"names": ["{sur}'s Potion of Haste", "{sur}'s Draught of Valor", "{sur}'s Elixir of Passage"],
                 "price": {"base": 40, "per_star": 15},
                 "effect": {"kind": "auto_pass_or_roll", "base": 2, "per_star": 1}},
  "magic":      {"names": ["{sur}'s Amulet of Fortune", "{sur}'s Charm of Warding", "{sur}'s Sigil of Power"],
                 "price": {"base": 150, "per_star": 50},
                 "effect": {"kind": "magic", "options": ["gold", "reroll", "power", "extra_slot"]}}
```

- `build_catalog(athletes, half, price_multiplier) -> list[Item]`: one `Item` per athlete, name
  chosen deterministically (seeded by athlete_id so both clients agree), price/effect scaled by
  the athlete's `stars`, price scaled by the half multiplier. Surname = last token of `name`.
- `Item` (pure dataclass): `item_id` (= athlete_id), `name`, `category`, `price`, `two_handed`,
  `persist` (`"infinite"`/`"round"`), `effect` (dict), `source_pos`, `stars`.
- **Loadout** (`src/game/loadout.py`): up to `game.loadout_size` (=6) items per fighter; at most
  one `two_handed` weapon; `extra_slot` magic raises the cap by 1. `can_add(item)` enforces rules;
  `total_cost()` sums prices. Consumables are consumed when used and free their slot next round.
- Offline/demo fallback: when fewer than 22 athletes are available (demo pool of 10), the catalog
  is simply built from whatever athletes exist; the shop shows those.

---

## 9. Party, persistence & leader-authoritative sync

- **Screens renamed**: "Create Room"/"Join Room" -> **"Create Party"/"Join Party"**.
  - Create Party: leader picks/creates a **party number**, the client generates the seed and writes
    the canonical party JSON to the relay; leader = first creator.
  - Join Party: enter **party number + username**. If the username already exists in the party,
    the member is **restored** (seat, gold view, items, wounds). Otherwise they take the next free
    seat (parties cap at 3). Username is the only re-entry credential.
- **Party JSON** (relay file, leader-authoritative). Extends the existing room file:

```json
{
  "party_id": "7K2",
  "seed": 99,
  "leader": "drpaj",
  "half": 1,
  "members": [
    {"username": "drpaj", "slot": 0, "items": ["fifa-123"], "alive": true, "wounds": 0}
  ],
  "treasury": 540,
  "dungeon": { "...DungeonState..." },
  "log": ["W1 @15' ..."],
  "window_picks": { "0": {"w": 2, "preds": ["goal:1","shot:3", "..."]} },
  "resolved_through_window": 1
}
```

- **Leader-authoritative resolution**: when a window closes, every member submits their picks to
  the relay; the leader's client reads all members' picks, computes the window result (bands ->
  tiles, Power, gate rolls, gold, log lines), advances `DungeonState`, and writes the canonical
  party JSON. Followers poll and render the leader's result; they never resolve the dungeon
  themselves. This replaces "every client runs identical RNG" (which only held when all inputs
  were identical — now picks differ per member).
- Relay (`php/soccer_api.php`) gains: up to 3 slots per party; rejoin-by-username; storage of the
  `dungeon`, `treasury`, `log`, and per-member `items`. Still PII-free (usernames are self-chosen).
- `src/sync/session_state.py` / `relay_client.py` gain party-aware read/write helpers and a
  `is_leader` flag (true for the creator's username).

---

## 10. Crawl log (pure: part of the window-resolution output)

Each window resolution returns a list of ASCII log lines appended to `log` and rendered in a
scrollable panel. Example:

```
W2 @30'  Shots EXACT +3 | Corners OFF +0 | Cards CLOSE +2 | Fouls NEAR +1
         Party advanced +6 -> depth 14/36
  GATE   Cave Troll (diff 7): Sword of Messi +2, Power +1, roll 4 = 7 -> PASS  +50g
  POWER  Goal CLOSE -> +1 Power (now 3)
```

Log lines are ASCII-only (per the project rule) since they are also written to the party file.

---

## 11. Party-size scaling

`party_size in {1,2,3}` scales the experience so smaller parties stay balanced and the final
completion % is comparable:
- **Total tiles** per half = `tiles_per_fighter_halfN * party_size` (sec. 6).
- **Monster difficulty** += `monster_difficulty_per_fighter * (party_size - 1)` (sec. 6).
- **Base treasury** = `base_treasury_per_fighter * party_size` (sec. 7).
- **Window advance** is the sum of each fighter's 4 progress-band steps, so 3 fighters advance
  ~3x faster through a ~3x-longer dungeon. Gate rolls use the party's best weapon/armor and total
  Power, so specialization (one fighter buys the big weapon, another armor, another magic) pays off.
- Solo play (sim mode) drives a 1-fighter party by default; a solo tester may also drive a
  3-fighter party locally for full-mechanic testing.

---

## 12. UI changes (`src/ui/`)

- **Shop screen** (new `src/ui/screens/shop_screen.py`, replaces draft in the flow): grid of
  generated items with PNG icons, price, the shared treasury balance, a 6-slot loadout strip,
  buy/sell, and constraint enforcement (one two-handed weapon, slot cap). Used pre-H1 and at the
  H2 re-buy phase.
- **Play screen** (`live_play_screen.py` extended): the same 5 dials per 15-min window; resolved
  window cells colored green/orange/red; a **depth meter at the bottom** (scrollable) with tile
  pips and gate markers; Power and wounds indicators; the real match scoreline kept in the header;
  party score shown as `Depth d/total (p%)`.
- **Crawl log panel**: scrollable text below the depth meter.
- **Graphics**: hand-authored PNGs in `src/assets/images/` (weapons, armor, potions, amulets, a few
  enemies, dungeon tile/gate art), loaded via `asset_loader`. A small registry maps category/tier
  -> sprite.
- Flow: Splash -> Party (create/join) -> Pregame -> **Shop** -> LivePlay (3 windows) ->
  Halftime/Shop(H2) -> LivePlay (3 windows) -> Final (% completed + leaderboard submit).

---

## 13. Scoring & highscore

- Party score = `depth_total / tiles_total_both_halves` as a percent (`src/game/score.py`).
- The end-of-half highscore submit (already wired) changes its payload from goals_for/against to
  **percent completed** (and depth), ranked descending. `highscore.php` + `highscore.html` updated
  to show "% dungeon" instead of a scoreline. Still PII-free.

---

## 14. Resume

The existing localStorage resume (`live_resume.py`) extends to capture the new state: loadout,
treasury (read-only mirror for followers; authoritative on leader), `DungeonState`, Power, wounds,
threat, crawl log, and per-window picks. `can_restore` continues to validate half + party
membership. Leader vs follower is recorded so a returning leader resumes authority.

---

## 15. Sim mode (test path for tomorrow)

- Recorded old World Cup matches in `assets/data/simulations/` (the 2018 final exists; add 2-3
  more, each carrying full lineups so the item catalog can be generated).
- Sim mode runs the full flow on one device with no relay and a fixed seed: pick a recorded match,
  buy a loadout, play 3+3 windows, watch the party descend, see the depth meter, colored windows,
  and crawl log. This is the deterministic mechanics sandbox.

---

## 16. Module map (new / changed)

Pure (`src/game/`, zero pygame, unit-tested):
- `bands.py` — band grading + window color.
- `power.py` — goal-prediction Power gains.
- `dungeon.py` — `DungeonState`, gate resolution, dice, wounds.
- `treasury.py` — gold awards, half economy.
- `items.py` — catalog generation from athletes + templates.
- `loadout.py` — per-fighter 6-slot loadout + constraints.
- `score.py` — percent-completed scoring.
- `party.py` — party model (members, slots, rejoin-by-username, leader).
- `window_resolver.py` — orchestrates a window: picks -> bands -> tiles -> gates -> gold -> log
  (the leader-authoritative resolution; pure, takes an injected RNG).

UI (`src/ui/`):
- `screens/party_screen.py` (rename/replace room), `screens/shop_screen.py` (new),
  `live_play_screen.py` (depth meter, colors, log, Power/wounds), `screens/status_screens.py`
  (final % completed), `flow.py` (new flow incl. shop + H2 re-buy), `asset_loader` + an image
  registry for PNG icons.

Sync (`src/sync/`): party-aware `relay_client.py` / `session_state.py`; `php/soccer_api.php`
3-slot party + dungeon/treasury/log storage + rejoin-by-username.

Config: new `bands`, `power`, `dungeon`, `economy` blocks; `game.window_seconds` 900,
`game.windows_per_half` 3, `game.loadout_size` 6; `assets/data/item_templates.json`.

Tests (`tests/`, pure only): `test_bands.py`, `test_power.py`, `test_dungeon.py`,
`test_treasury.py`, `test_items.py`, `test_loadout.py`, `test_score.py`, `test_party.py`,
`test_window_resolver.py`. Smoke (`TOOLS/smoke_flow.py`): a `dungeon_smoke` driving a full
sim half (shop -> 3 windows -> gates -> final %) and a party-size-scaling assertion.

---

## 16.5 Retired / repurposed from the current game
- **Retired** (the old shot-scoring loop): `meters.py` (success/concede), `shot.py`,
  archetype shot-conversion in `powers.py`, the per-window **active-athlete rotation**
  (`roster.use`/`active_id`/`use_power`), and the cinematic shoot animation. There is no longer a
  "player who takes the shot" — fighters are the party members and the 6 items are equipment, not a
  rotating hand of athletes.
- **Repurposed**: `athlete.py` (`broad_position`, `stars`) now feeds **item generation** (sec. 8),
  not a draft hand. The live feed's lineup parsing and `actuals_from_raw` (stat deltas per window)
  are reused unchanged to grade bands. The existing `live_resume` and highscore wiring are extended,
  not replaced.

## 17. Build order (all phases ship the full thing)

1. **Mechanics + economy + shop + graphics + crawl log in SIM mode** (single device, deterministic).
   Fully testable tomorrow.
2. **3-player party relay + leader-authoritative persistence + rejoin-by-username.**
3. **Polish**: H2 re-buy balancing, more recorded matches, highscore "% dungeon", resume of new state.

---

## 18. Open risks
- Relay rework (2 slots -> 3-slot party + dungeon state) is the riskiest piece and is hardest to
  verify without 3 live clients; sim mode de-risks the mechanics independently of it.
- Hand-authored PNG volume — keep the icon set small (one sprite per category/tier + ~4 enemies).
- Balancing party-size scaling will need a tuning pass against a recorded match (config-only).
