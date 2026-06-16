# Coop Soccer Prediction Game — Design Spec

Date: 2026-06-16
Status: Approved (brainstorming complete; ready for implementation planning)
Supersedes: the open questions and FIFA/Balldontlie assumptions in `DESIGN.md` for the
soccer v1. `DESIGN.md` remains the broader project reference; this spec is authoritative
for the soccer coop v1 mechanics, data source, and architecture.

---

## 1. Concept

A cooperative, 2-player, mobile-web-first soccer prediction game. Two partners watch the
same live soccer match. Before kickoff each partner independently drafts a hand of real
athletes from today's actual lineup. During the match, on a fixed window cadence, each
partner submits over/under predictions on loggable match stats. Prediction accuracy feeds
two per-player local meters (success and concede). When a meter fills it triggers a shot
ATTEMPT (not an automatic goal), resolved by a conversion-percentage roll tied to the
player's currently active drafted athlete. Goals scored are added to a SHARED team score
that both partners see; goals conceded are added to a shared opponent score.

The two partners cooperate against a shared opponent. The opponent is either a virtual
construct or one of the two real teams in the match — a thematic choice made at session
start that does NOT change the meter/scoring mechanics (same engine either way; real-team
mode additionally shows the real scoreline alongside the game score at full time, for
flavour only).

This is explicitly a "generic" first version: the theme, win goal, co-op-vs-competitive
framing, and individual mechanics are all expected to change. Every quantitative value
lives in config/data files so the game can be rebalanced and re-themed without code changes.

---

## 2. Hard Constraints (inherited and discovered)

These bound the design and must not be silently violated.

1. **Mobile web is the target form factor.** Portrait orientation primary. pygbag/WASM
   build via the existing `WEB_BUILD/index_mobile.html` template and
   `TOOLS/build_web_mobile.py`. UI density must suit a phone screen (limited picks per
   window, large touch targets).
2. **The relay is a PHP script writing to a flat file.** Communication budget between
   clients is SMALL. Only compact data crosses the wire (drafts, prediction codes, score
   result codes, the cached feed snapshot). No large blobs, no per-frame state, no meter
   state.
3. **Blind prediction timing.** Predictions for the next window are locked while the
   current window is still playing out. Results are revealed only after the following
   window opens. You commit without knowing.
4. **Cards come from the real day's lineup.** No fictional athletes. The pool is whatever
   the live API returns for today's match lineups.
5. **Events are only what the feed reports.** Scoring vocabulary is bounded by the API's
   available stats/events.
6. **Architecture rules from CLAUDE.md.** `src/game/` is pure Python, zero pygame, fully
   testable. `src/ui/` holds all pygame. `config/game_config.json` holds all constants.
   `tests/` tests `src/game/` only. Type hints on every function. No globals. ASCII-only
   in all printed/logged/`.md` output (Unicode allowed only inside rendered pygame
   surfaces).

---

## 3. Data Source (CHANGED from DESIGN.md)

### 3.1 Why the change

DESIGN.md assumed the Balldontlie FIFA API free tier (5 req/min, key required) provides
matches, lineups, events, and stats. This is FALSE. Verified against the Balldontlie FIFA
OpenAPI spec and pricing page (2026-06): the free tier exposes only Teams and Stadiums.
Matches, lineups, match_events, team_match_stats, player_match_stats, and match_shots all
require the GOAT tier at $39.99/month. The soccer game cannot be built on Balldontlie's
free tier.

### 3.2 Chosen source: API-Football (api-football.com / api-sports.io)

- Free tier unlocks ALL endpoints (fixtures, lineups, events, statistics) — no per-feature
  paywall.
- Free limits: ~100 requests/day, 10 requests/minute. Live data updates ~every 15s on all
  plans.
- **UNVERIFIED RISK:** API-Football docs mention free-tier "season" restrictions. It is not
  confirmed from outside whether this blocks current/live-season fixtures or only old
  historical leagues (their docs site blocks automated fetching). This MUST be verified
  with a real free key + live smoke test as the first implementation step (see 3.4).

### 3.3 Feed access architecture (CHANGED from DESIGN.md)

DESIGN.md had each client poll the sports API directly with an embedded key. Changed to a
PHP-proxied cache:

- The PHP relay fetches today's fixture -> lineups -> live events/stats on a server-side
  timer and caches the latest snapshot to a flat file.
- Both clients GET the cached snapshot from the relay; clients never call API-Football
  directly.
- Benefit: API key stays server-side (not shipped in the public WASM build); the ~100
  req/day quota is shared once, not doubled across two clients.
- Polling cadence: 120s server-side (well inside 10 req/min), finer than the 5-minute game
  window needs.
- Still satisfies the "PHP is the only server-side component" non-goal — no Python backend
  is introduced.

### 3.4 Verify-early task (MANDATORY first implementation step)

Before any game logic is built on real data: sign up for a free API-Football key, run a
throwaway smoke test confirming that TODAY's live fixture, its lineups, and in-window stat
deltas actually return on the free tier. If they do not, fall back to the mock/replay feed
(see 7.2) and revisit the data source. Do not build on an unverified assumption.

---

## 4. Generic Engine Boundary

`src/game/` is sport-agnostic. It contains NO pygame imports and NO soccer- or
API-Football-specific string literals.

Core types in `src/game/`:
- `SportEvent` — normalized event/stat-snapshot record.
- `EventFeed` (Protocol) — interface the game logic depends on; yields `SportEvent`s and
  window stat snapshots. Implementations live elsewhere.
- `Prediction` — a player's over/under pick for a window (compact code + parsed form).
- `Meter` — a fillable/fireable/resettable counter (used for both success and concede).
- `Roster` / `DraftedAthlete` — a player's hand and the athletes in it.
- `Archetype` / `PowerEffect` — position archetype and its two-part power.
- Scoring, grading, meter, rotation, and power-resolution functions — pure, deterministic.

The soccer feed adapter (API-Football JSON -> `SportEvent`) lives behind the `EventFeed`
protocol in a feed module (`src/game/feed/` or `src/feed/` — finalized in the plan), NOT in
the core logic. Swapping sports later = a new adapter, with game logic untouched.

A mock/replay feed implementing the same protocol exists for development and tests.

---

## 5. Draft & Roster

- **Pool:** the full lineup (starters + substitutes) of BOTH real teams in today's match,
  as returned by the API-Football lineup endpoint.
- **Format:** each partner independently drafts a hand simultaneously. No alternating/snake
  draft, no mid-draft coordination required.
- **Duplicates allowed:** both partners may hold the same athlete. Exclusivity is not
  enforced (consistent with keeping cross-client communication light and the brief's note
  that the infrastructure does not prevent duplicate picks).
- **Roster size:** 6 athletes per player. Config: `game.roster_size` (default 6).
- **Per-athlete data:** name, position (broad, from API), team, jersey number, plus a
  derived archetype and star rating and power (see Section 8).
- **Opponent mode** is chosen at this stage: virtual, or real (home or away). Stored with
  the draft in the relay record. Mechanics are identical across modes; only flavour/full-
  time comparison differs.
- **Transmission:** each player's hand (6 athlete-ID strings) is POSTed to the relay at
  draft-lock, so each client knows both hands entering the live phase.

---

## 6. Window / Prediction / Meter Loop (core mechanic)

### 6.1 Timing (pipelined, blind)

- Window length: 5 minutes. Config: `game.window_seconds` (default 300).
- While window N plays out in the real match, each partner locks predictions for window N+1
  (blind — window N has not resolved yet).
- When window N closes (= window N+1 opens): pull window N's actual numbers, grade the
  locked predictions for window N, update meters, resolve any fired shot attempts, reveal
  results. Repeat.

### 6.2 What you predict

- Each window presents a small, config-driven menu of loggable stats.
- Incident-count stats (e.g. `goal`, `card`, `substitution`): count of occurrences within
  the window.
- Cumulative-delta stats (e.g. `corners`, `shots_on_target`, `saves`, `fouls`): end-of-
  window value minus start-of-window value.
- The exact predictable-stat set is config-driven and finalized only AFTER the 3.4 smoke
  test confirms which stats API-Football actually returns per window on the free tier.
- Max predictions per window: 2. Config: `game.max_predictions_per_window` (default 2).
- Prediction code format: compact string, e.g. `"corner:o3"` (stat:over/under+number),
  to stay within the flat-file relay budget. Exact grammar finalized in the plan.

### 6.3 Active player rotation

- Each window the player selects one athlete from their hand as the ACTIVE player for that
  window.
- Selection is restricted to athletes not yet used in the current cycle. When all 6 have
  been used, the cycle resets and all 6 become available again.
- The active player determines (a) which power can be activated this window, and (b) the
  shot-conversion % used if the success meter fires this window.

### 6.4 Scoring bands (threshold band, not a smooth curve)

For each graded prediction, compare predicted count to actual count:
- Exact match -> +2 to the player's own local SUCCESS meter.
- Off by exactly 1 (either direction) -> +1 to the success meter.
- Off by more than 1 -> +2 to the player's own local CONCEDE meter.

All band values are config: `scoring.exact_credit` (2), `scoring.near_credit` (1),
`scoring.miss_concede` (2), `scoring.near_band` (1).

### 6.5 Meters fire shot ATTEMPTS, not automatic goals

- Both meters are per-player and LOCAL (computed from that player's own predictions + the
  shared feed). Thresholds are config: `meter.success_threshold`,
  `meter.concede_threshold`.
- Success meter crosses threshold -> shot attempt FOR. Resolve by rolling against the
  active player's conversion %. Hit -> a goal is added to the shared team score. Miss ->
  no goal. Either way the success meter resets to 0.
- Concede meter crosses threshold -> shot attempt AGAINST. Resolve using a randomly drawn
  athlete from the pool EXCLUDING the player's own 6 drafted athletes (a player you did not
  pick threatens you), rolling against that athlete's conversion %. Hit -> a goal is added
  to the shared opponent score. Miss -> no goal. Either way the concede meter resets to 0.
- The GK power (Section 8) can negate a concede shot attempt before the roll.

### 6.6 Determinism note (deliberate extension of the brief's RNG contract)

The brief's original contract: only drafts and predictions cross the wire; everything else
is recomputed identically by both clients from shared seed + shared API data. Shot-attempt
rolls are LOCAL randomness (each player's meters are local and depend on that player's own
picks). Therefore the RESULT of a fired shot attempt (goal / no-goal, for / against) is
posted to the relay as a tiny `score_event` code, rather than requiring the partner's
client to replay the dice roll. This keeps relay payloads tiny and avoids cross-client RNG
synchronization for this mechanic. This is an intentional, documented extension of the
original single-seed contract.

### 6.7 Shared score

- Each partner's fired goals (for) and conceded goals (against) post to the relay as
  `score_event` codes.
- The shared team score = sum of both partners' goals-for. The shared opponent score = sum
  of both partners' goals-against. Both partners see both totals.

### 6.8 Session end

- When the live match status reaches full-time, the session ends.
- Final shared team score vs. shared opponent score is shown.
- In real-team opponent mode, the real match scoreline is also shown side-by-side, for
  flavour only (no mechanical link).

---

## 7. State Model & Relay Payload

### 7.1 Local (recomputed each client, never transmitted)

- Both rosters (own known at draft, partner's received at draft-lock).
- The shared feed snapshot (fetched from the relay cache).
- Own predictions per window; meter states; rotation/used-player state; running local
  tallies. All derived; none transmitted.

### 7.2 Relay flat file (kept small)

Per session, only:
- `seed`, `sport`, `fixture_id`, `opponent_mode`, `created_at`
- `draft.player_a` / `draft.player_b`: 6 athlete-ID strings each
- `windows[N]`: each player's <=2 prediction codes + active-player index + power-on flag
- `score_events[]`: compact goal result codes (slot, window, for/against, hit/miss)
- `feed_cache`: the latest cached feed snapshot the relay fetched (or stored in a separate
  cache file — finalized in the plan)
- NO meter state, NO event log, NO per-frame state.

### 7.3 Mock/replay feed (development + tests)

A canned/replayable match feed implementing the `EventFeed` protocol, so the full
draft -> predict -> meter -> score loop is playable and testable with zero API cost and
deterministically. This is also the fallback if the 3.4 smoke test fails.

---

## 8. Player Powers & Ratings

### 8.1 Archetypes (11)

Each drafted athlete is mapped from its broad API position into one of 11 finer archetypes,
deterministically via a seeded hash of the athlete ID within its broad position bucket
(reproducible, not re-rolled each load):
- GK
- Defender -> Center Back, Full Back, Wing Back
- Midfielder -> Defensive Mid, Central Mid, Attacking Mid
- Attacker -> Winger, Second Striker, Striker

### 8.2 Star rating (1-5)

Assigned per athlete via seeded hash of the athlete ID. This is an IN-GAME rating, not a
real-world stat (the free API does not expose skill ratings) — approved as a deliberate
game construct. Star rating scales both the athlete's shot-conversion % and its power
magnitude, e.g. `magnitude = base * (0.6 + 0.2 * stars)`. Exact formula is config/data.

### 8.3 Two-part powers (22 effects, fully data-driven)

Each archetype has a power with two parts, giving 22 tunable effects total:
1. This-window effect — an immediate boost (extra success credit, reduced concede credit,
   conversion % bump, or shot negation).
2. Next-window effect — usually a tradeoff cost applied automatically to the following
   window; occasionally a bonus.

Three generating patterns:
- Attack-leaning (Striker, Second Striker, Winger, Attacking Mid): strong this-window
  boost; small concede-credit penalty next window.
- Defense-leaning (GK, Center Back, Full Back, Wing Back, Defensive Mid): strong this-window
  defensive boost; small success-credit penalty next window.
- Playmaker (Central Mid): small this-window effect; POSITIVE carryover next window (the one
  archetype with no cost, balanced by a weak immediate effect).

Baseline conversion %: highest for Striker (~35%), lowest for GK (~10%), others between —
all config/data values. Power usage is opt-in per window (toggle when locking picks), only
available when that archetype's athlete is the active player.

All 22 effects (archetype, this-window formula, next-window formula, base magnitude) and
all conversion baselines live in an editable data file: `assets/data/powers.json`. NOT
hardcoded.

---

## 9. Config & Data Files

- `config/game_config.json` — all scalar constants: `window_seconds`, `roster_size`,
  `max_predictions_per_window`, scoring band values, meter thresholds, star-scaling
  formula coefficients, polling cadence, relay URL, screen dimensions, colors.
- `assets/data/powers.json` — the 22 power effects + conversion baselines per archetype,
  editable for rebalancing.
- `assets/data/stats_menu.json` (or a config section) — the predictable-stat menu,
  finalized after the 3.4 smoke test.

No magic numbers in code (CLAUDE.md rule).

---

## 10. Testing Strategy

- pytest on `src/game/` only; no pygame in tests.
- Coverage: band scoring; meter fill/fire/reset; shot-conversion rolls (seeded ->
  deterministic); archetype + star assignment determinism (same ID -> same archetype/star
  every run); power this-window and next-window application; prediction grading from a
  fixture feed snapshot; rotation (used-player exclusion, cycle reset); shared-score
  aggregation from `score_event` codes.
- Fixture-driven feed adapter tests: captured API-Football JSON in `tests/fixtures/` ->
  adapter -> `SportEvent`. Never hits the live API in tests.

---

## 11. Build & Deployment Scope

- pygbag/WASM, portrait/mobile-web primary, via `TOOLS/build_web_mobile.py` and
  `WEB_BUILD/index_mobile.html`.
- v1 INCLUDES: soccer feed (API-Football, verified or mock fallback), coop draft,
  windowed blind predictions, threshold-band scoring, dual local meters, shot-attempt
  conversion, rotation, 11 archetypes + star ratings + 22 data-driven powers, opponent-mode
  choice (virtual/real), shared score, full-time summary, PHP relay (picks + score events +
  feed cache).
- v1 EXCLUDES: NHL wiring (engine stays generic so it can be added later), leaderboard /
  async-solo mode, audio polish, real player-face art (stylized name + position +
  archetype + star cards instead).

---

## 12. Open Items Deferred to the Plan

- Exact prediction-code grammar.
- Exact predictable-stat menu (pending 3.4 smoke test).
- Whether feed cache is a field in the session file or a separate cache file.
- Exact module path for the feed adapter (`src/game/feed/` vs `src/feed/`).
- Exact star-to-conversion and star-to-magnitude formula coefficients (start in config,
  tune later).
