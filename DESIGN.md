# PJAB's Fanbidextrous Game — The Idea

*A browser-playable 2-player prediction game built with pygame-ce and deployed via pygbag,
driven by live NHL and FIFA World Cup 2026 event feeds. Before the game starts, each player
drafts real athletes from the day's actual lineup. Points are scored when a drafted player
causes an event during the live game.*

---

## 0. First description of the project

I want to build a generic version of the soccer version of this to start.  The main goals are this is a coop, I want
  to be able to draft with my partner different players.  Then with the prediction mechanic, we somehow collectively
  get passes (our own since game state is based on our choices) and we collectively get a score against a shared
  opponent.  Read the files and start implementing this with the superpower.
---

## 1. Project Vision

- What the two players do and feel during a live game
- They draft the players in the game between each other
- The draft phase: how players pick athletes and why it matters - different positions and different skill set allow for using in certain windows for buffs?
- The core event loop (athlete does something live -> owner scores) - we predict for events in a 5 minute window (in an over under fashion) and in that window depending on the event you have good statistical things happen in a buildup to goal for or against.  While the past window is happening, you are making the predictions for the next window.
- The tone and visual style is a soccer game (maybe with player's faces or stylized names and position with power.  Each of the events is an over under where you set the number of events in a window where a perfect prediction is better then over is okay, but gets worse with differential.

The game targets **browser-first delivery** via pygbag/WASM so it runs at a URL with no
install. The same codebase runs locally with `python -m pygbag` for development. Live event
data and the draft pool are fetched by a lightweight central server and cached so neither
player ever hits a third-party rate limit directly.  The main focus is on a cellphone html version.

---

## 2. Goals and Non-Goals

**v1 goals:**
- [ ] Pre-game draft: each player picks athletes from the actual day's lineup
- [ ] Draft pool built from NHL boxscore OR Balldontlie FIFA match detail (two-step query)
- [ ] NHL live event feed: play-by-play polled every 120 seconds per client
- [ ] FIFA/World Cup 2026 live event feed: Balldontlie polled every 120 seconds per client
- [ ] Point scoring when a drafted athlete triggers a live event
- [ ] Two players on separate browsers, synced via PHP relay on drpeterjamieson.com
- [ ] PHP relay transmits only per-window picks; all other state is locally deterministic
- [ ] RNG seeded once per session; both clients run identical game logic from the same seed
- [ ] Single static HTML folder deployable to GitHub Pages / Netlify / itch.io
- [ ] Works on desktop browsers (Chrome, Firefox, Edge)

**v2+ goals:**
- [ ] Betting-odds-based dynamic point multipliers (Balldontlie odds data)
- [ ] Persistent draft history and leaderboard across sessions
- [ ] Mobile browser support
- [ ] More sports feeds

**Non-goals:**
- Native installer / .exe
- More than 2 simultaneous players in v1
- Mobile-native app
- A persistent Python game server (PHP relay is the only server-side component)

---

## 3. Tech Stack (Pinned)

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | pygbag WASM target requires 3.11 |
| Game library | pygame-ce | Community edition; same `import pygame` namespace |
| Web build | pygbag | Compiles to WASM, serves via asyncio event loop |
| Sync relay | PHP script on drpeterjamieson.com | Stores and serves per-window picks only; no game logic |
| Sports data -- NHL | Official NHL API (`api-web.nhle.com/v1`) | Free, no key, schedule + boxscore + play-by-play |
| Sports data -- FIFA | Balldontlie FIFA API (`api.balldontlie.io/fifa/v1`) | Free tier: 5 req/min; API key required |
| Data schemas | Pydantic v2 | DraftPool, DraftedAthlete, SportEvent, GameSession all validated |
| Testing | pytest | Logic tests only; no GUI test runner needed |
| Lint/format | ruff, black | Standard Python tooling |
| Dependency mgmt | pip + venv | No uv installed on target machine |

### pygame-ce vs pygame notes
- Install `pygame-ce`, NOT `pygame` (they conflict -- never install both).
- `import pygame` works identically; pygame-ce is a drop-in superset.

### pygbag async loop requirement
Every game MUST follow this pattern or it will freeze the browser:

```python
import asyncio
import pygame

async def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

        # update and draw here

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)  # REQUIRED -- yields to browser event loop

asyncio.run(main())
```

---

## 4. Pre-Game Draft System

Before each session the cache server runs a two-step query for the chosen sport to build
the **draft pool** -- the set of real athletes available to pick from. Both steps complete
before the game UI opens the draft screen. The draft pool is served to both players from
the cache server; neither client calls a sports API directly.

The two-step pattern is the same for both sports:
1. Query today's schedule to get active game IDs.
2. For each game ID, query the roster/boxscore endpoint to get the actual player lineup.

Lineups have timing constraints that the server must handle gracefully:
- **NHL:** lineups (skaters + goalies in the boxscore) are published ~20-30 minutes before
  puck drop. Querying too early returns empty arrays. The server retries on the next 120s tick.
- **FIFA:** official lineups are published ~60 minutes before kickoff. Same retry logic.

---

### 4.1 NHL Draft Pool — Two-Step Query

**Step 1: Get today's game IDs**
```
GET https://api-web.nhle.com/v1/schedule/now
```
Parse `gameWeek[].games[]` filtering for today's date. Extract `game.id`,
`game.homeTeam.abbrev`, `game.awayTeam.abbrev`.

**Step 2: Get lineup for each game**
```
GET https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore
```
Parse `homeTeam.skaters[]`, `homeTeam.goalies[]`, `awayTeam.skaters[]`, `awayTeam.goalies[]`.

Each player object yields:
```json
{
  "playerId": 8478402,
  "name": { "default": "Auston Matthews" },
  "position": "C",
  "team": "TOR"
}
```

**Normalized to `DraftedAthlete`:**
```json
{
  "athlete_id": "nhl-8478402",
  "sport": "nhl",
  "name": "Auston Matthews",
  "position": "C",
  "team": "TOR",
  "game_id": "2026020512",
  "matchup": "BOS @ TOR"
}
```

**Rate limit:** No documented limit. One request per game is fine. With 10-15 games on a
typical NHL night, the full draft pool query takes well under 1 minute.

---

### 4.2 FIFA Draft Pool — Two-Step Query

**Step 1: Get today's match IDs**
```
GET https://api.balldontlie.io/fifa/v1/matches?dates[]=2026-06-05
Header: Authorization: {BALLDONTLIE_API_KEY}
```
Parse `data[]`, extract `match.id`, `match.home_team.name`, `match.away_team.name`.

**Step 2: Get lineup for each match**
```
GET https://api.balldontlie.io/fifa/v1/matches/{match_id}
Header: Authorization: {BALLDONTLIE_API_KEY}
```
Parse `data.home_team.lineup.starting_eleven[]` and `data.home_team.lineup.substitutes[]`
(same structure for `away_team`).

Each player object yields:
```json
{
  "id": 5501,
  "name": "Alphonso Davies",
  "jersey_number": 19
}
```

**Rate limit:** 5 req/min on the free tier. With potentially 8 World Cup matches per day,
the server must pause **12 seconds between each match detail request** to stay under the cap.
The `time.sleep(12)` call is mandatory in the server polling loop, not optional.

**Normalized to `DraftedAthlete`:**
```json
{
  "athlete_id": "fifa-5501",
  "sport": "fifa",
  "name": "Alphonso Davies",
  "position": null,
  "team": "Canada",
  "game_id": "901",
  "matchup": "Morocco vs Canada",
  "jersey_number": 19
}
```

---

### 4.3 Draft Pool Schema

The `DraftPool` is the output of the two-step query. It is stored in the cache server's
SQLite database and served to clients at session start.

```json
{
  "schema_version": "1.0.0",
  "sport": "nhl",
  "built_at": "2026-06-05T18:30:00Z",
  "games": [
    {
      "game_id": "2026020512",
      "matchup": "BOS @ TOR",
      "status": "pre_game",
      "athletes": [ ... list of DraftedAthlete ... ]
    }
  ]
}
```

`status` values: `pre_game` (lineup not yet published), `lineup_confirmed` (ready to draft),
`in_progress` (game live), `final`.

---

### 4.4 Draft Session Flow

1. Server builds `DraftPool` on startup (or on demand) using the two-step queries above.
2. Game UI receives `DraftPool` from cache server at `GET /draft-pool`.
3. **Pick screen:** Players alternate picking athletes (snake draft or simultaneous -- TBD).
   Each player builds a roster of N athletes. N is TBD but suggested 5-8 for a single game.
4. Picks are POSTed to the cache server: `POST /draft` with `{player_id, athlete_id}`.
5. Server saves picks to SQLite table `draft_picks(session_id, player_slot, athlete_id, game_id)`.
6. Once both players have locked their rosters, the server flips to **live event mode**:
   polling play-by-play / match events at 120-second intervals.
7. On each 120s tick the server checks every new `SportEvent` for a `playerId` that matches
   any drafted athlete. Matches are scored and pushed to the `/events/*` endpoint.

---

## 5. Live Sports Event Feeds

Both feeds are polled by the **central cache server** at a 120-second interval once a game
is live. Players receive events from the cache, never from the third-party API directly.

The 120-second polling interval is deliberately conservative:
- NHL: no documented rate limit, but IP blocking occurs on spam; 120s is safe.
- Balldontlie free tier: 5 req/min = 0.5 req/min at 120s, leaving a full retry budget.
- Sports events that matter for scoring (goals, penalties, cards) happen at a cadence
  where 120s resolution is meaningful without being noisy.

---

### 5.1 NHL — Official API (`api-web.nhle.com/v1`)

**Access:** Completely public. No API key. No daily cap. No registration.

**Live event endpoint:**
```
GET https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play
```

**Raw event shape:**
```json
{
  "eventId": 312,
  "periodDescriptor": { "number": 2, "periodType": "REG" },
  "timeInPeriod": "08:43",
  "timeRemaining": "11:17",
  "situationCode": "1551",
  "typeDescKey": "goal",
  "details": {
    "scoringPlayerId": 8478402,
    "assist1PlayerId": 8481528,
    "shotType": "wrist",
    "xCoord": 68,
    "yCoord": -12,
    "goalModifier": "even-strength"
  }
}
```

**Event types and their draft scoring relevance:**

| typeDescKey | Draft relevance | Player ID field in details |
|---|---|---|
| `goal` | Primary scoring event; scorer + assists | `scoringPlayerId`, `assist1PlayerId`, `assist2PlayerId` |
| `shot-on-goal` | Secondary event; shooter | `shootingPlayerId` |
| `missed-shot` | Optional event; shooter | `shootingPlayerId` |
| `blocked-shot` | Optional event; blocker + shooter | `blockingPlayerId`, `shootingPlayerId` |
| `hit` | Optional event; hitter + hittee | `hittingPlayerId`, `hitteePlayerId` |
| `giveaway` | Optional event; player who gave it away | `playerId` |
| `takeaway` | Optional event; player who took it | `playerId` |
| `faceoff` | Optional event; winner + loser | `winningPlayerId`, `losingPlayerId` |
| `penalty` | Secondary scoring event; penalized player | `committedByPlayerId` |
| `stoppage` | No player attribution; not scored | -- |

The `scoringPlayerId` in a `goal` event is the direct link from live event to drafted athlete.
The server looks up `scoringPlayerId` in the `draft_picks` table to award points.

**Additional fields used for game logic:**
- `timeInPeriod` -- clock string for display
- `periodDescriptor.number` -- period 1/2/3/OT
- `details.xCoord`, `details.yCoord` -- ice coordinates (feet from center); used for
  zone-based bonus predictions ("goal scored from the slot")
- `details.goalModifier` -- even-strength / power-play / short-handed / empty-net;
  used for multiplier bonuses

---

### 5.2 FIFA — Balldontlie API (`api.balldontlie.io/fifa/v1`)

**Access:** Free tier, API key required. 5 req/min rate limit.

**Live event endpoint:**
```
GET https://api.balldontlie.io/fifa/v1/matches/{match_id}/events
Header: Authorization: {BALLDONTLIE_API_KEY}
```

**Raw event shape:**
```json
{
  "id": 4821,
  "match_id": 901,
  "type": "goal",
  "minute": 34,
  "extra_time_minute": null,
  "team": { "id": 12, "name": "Canada", "abbreviation": "CAN" },
  "player": { "id": 5501, "name": "Alphonso Davies" },
  "detail": "Normal Goal",
  "comments": null
}
```

**Event types and their draft scoring relevance:**

| type value | detail value | Draft relevance | Player ID field |
|---|---|---|---|
| `goal` | `Normal Goal` | Primary scoring event | `player.id` |
| `goal` | `Own Goal` | Primary event; negative for team | `player.id` |
| `goal` | `Penalty` | Primary event; penalty scorer | `player.id` |
| `card` | `Yellow Card` | Secondary event | `player.id` |
| `card` | `Yellow Red Card` | Secondary event (send-off) | `player.id` |
| `card` | `Red Card` | Secondary event (send-off) | `player.id` |
| `subst` | -- | Optional event; player coming off | `player.id` |
| `var` | -- | Situational; no direct player attr | -- |

The `player.id` in any event is the direct link from live event to drafted athlete.
The server looks up `player.id` (prefixed as `"fifa-{id}"`) in the `draft_picks` table.

**Macro match state** (polled from the match endpoint on the same 120s tick):
- `status`: `NS`, `1H`, `HT`, `2H`, `ET`, `PEN`, `FT`
- `score.home` / `score.away`: current integers
- Used to open/close prediction windows and display the live scoreboard.

---

### 5.3 Client Architecture — No Central Game Server

Both clients are fully self-contained pygbag WASM builds running in the browser. There is
no Python backend process. Each client independently fetches live sports data and runs all
game logic locally. The only server-side component is the PHP sync relay.

```
CLIENT A (browser)                          CLIENT B (browser)
  |                                            |
  +-- polls NHL/FIFA API every 120s           +-- polls NHL/FIFA API every 120s
  |    (same endpoints, same data)             |    (same endpoints, same data)
  |                                            |
  +-- runs game logic with RNG seed S         +-- runs game logic with RNG seed S
  |    (identical state to Client B)           |    (identical state to Client A)
  |                                            |
  +-- at window close: POST pick to PHP  -->  PHP relay (drpeterjamieson.com/game/sync.php)
  |                                       <-- GET opponent pick from PHP
  |                                            |
  +-- both advance to next window             +-- both advance to next window
       with full knowledge of both picks           with full knowledge of both picks
```

**Why this works:** Both clients read the same API data at the same 120-second cadence.
They process events in the same order using the same RNG seed. Game state diverges only
at the moment a player makes a pick -- that pick is the only thing that needs to cross
the wire. Everything else (draft pool ordering, event display, animations, scoring math)
is deterministic from the shared seed and the shared API data.

**PHP relay endpoints (read/write picks only):**
- `GET  https://drpeterjamieson.com/game/sync.php?session=CODE&window=N`
  Returns: `{"window": N, "player_a_pick": "...", "player_b_pick": "...", "rng_seed": S}`
  Either pick field is `null` if that player has not yet submitted for this window.
- `POST https://drpeterjamieson.com/game/sync.php`
  Body: `{"session": "CODE", "slot": 0, "window": N, "pick": "PICK_STRING"}`
  Returns: `{"ok": true}`

**Session join flow:**
1. Player A opens the game, gets a 4-character SESSION_CODE, sees a "waiting for player B" screen.
   Client A generates RNG_SEED (current Unix timestamp) and POSTs it to the relay as part of
   session creation.
2. Player A shares SESSION_CODE with Player B out-of-band (text, voice).
3. Player B enters SESSION_CODE on the join screen. Client B GETs the relay, reads RNG_SEED,
   calls `random.seed(RNG_SEED)`. Both clients are now locked to the same RNG state.
4. Draft proceeds. Each client shows the same draft pool (same API data + same RNG ordering).
   Picks are POSTed to the relay as they are made; each client polls the relay to see the
   opponent's pick before advancing.

---

## 6. Normalized SportEvent Schema

Raw NHL and raw FIFA JSON are structurally incompatible. The `normalize.py` layer on the
server converts both into a shared `SportEvent` before anything else touches the data.
The pygame client and the scoring engine only ever see `SportEvent` objects.

```json
{
  "schema_version": "1.0.0",
  "sport": "nhl",
  "event_id": "nhl-312",
  "event_type": "goal",
  "athlete_ids": ["nhl-8478402", "nhl-8481528"],
  "team": "TOR",
  "period_or_half": 2,
  "clock": "08:43",
  "detail": "even-strength",
  "raw_coords": { "x": 68, "y": -12 },
  "received_at": "2026-06-05T20:43:00Z"
}
```

Key fields:
- `athlete_ids` -- list of `"{sport}-{player_id}"` strings; can be multiple (scorer + assists,
  hitter + hittee). The scoring engine checks each against `draft_picks`.
- `event_type` -- normalized string consistent across both sports (see tables in Section 5).
- `detail` -- sport-specific qualifier: goal strength for NHL, card color for FIFA, etc.
- `raw_coords` -- present for NHL only (feet from center ice); null for FIFA.

---

## 7. State Model — Client-Side and PHP Relay

There is no server-side database. All game state lives in two places:

**1. In-memory Python objects on each client** (lost when the browser tab closes -- v1 only):
- `DraftPool`: list of `DraftedAthlete` objects, ordered by the shared RNG
- `DraftPicks`: dict mapping `player_slot -> [athlete_id, ...]`
- `EventLog`: list of `SportEvent` objects seen so far this session
- `WindowPicks`: dict mapping `window_number -> {slot: pick_string}` for all windows
- `SessionScores`: dict mapping `player_slot -> int` running point totals

**2. PHP relay flat JSON file** (one file per session, lives on drpeterjamieson.com):

```json
{
  "session": "X7K2",
  "rng_seed": 1749168000,
  "sport": "nhl",
  "game_id": "2026020512",
  "created_at": "2026-06-05T18:00:00Z",
  "windows": {
    "1": { "player_a_pick": "goal",    "player_b_pick": "penalty" },
    "2": { "player_a_pick": "hit",     "player_b_pick": null },
    "3": { "player_a_pick": null,      "player_b_pick": null }
  },
  "draft": {
    "player_a": ["nhl-8478402", "nhl-8481528", "nhl-8479318"],
    "player_b": ["nhl-8480012", "nhl-8471675", "nhl-8477934"]
  }
}
```

The PHP script reads and writes this file atomically (file lock). The only fields written
after session creation are `windows[N].player_X_pick` and `draft.player_X`.
Everything else (scores, event log, game state) is computed locally by each client from
the same inputs: shared seed + shared API data + known picks from the relay file.

**RNG seed contract (critical -- never break this):**
- Seed is set ONCE: `random.seed(RNG_SEED)` called before any randomized operation.
- The only randomized operation in v1 is draft pool ordering: `random.shuffle(athlete_list)`.
- Both clients call `random.shuffle` on the same athlete list (same API data) with the same
  seed, producing identical ordering. The draft board looks the same on both screens.
- No other game logic uses `random` -- event scoring is deterministic from API data alone.
- If any new randomized operation is added, it MUST be documented here and it MUST be called
  in the same position in the call sequence on both clients, or state diverges silently.

---

## 8. Repository Layout

```
fanbidextrous/
|
+-- README.md
+-- pyproject.toml
+-- .gitignore
+-- .env.example                     # BALLDONTLIE_API_KEY=your_key_here
|
+-- php/                             # PHP relay -- deploy to drpeterjamieson.com/game/
|   +-- sync.php                     # GET: return session JSON. POST: write a pick or draft.
|   +-- cleanup.php                  # Deletes session files older than 24h (run via cron)
|   \-- README.md                    # Deploy instructions, endpoint reference
|
+-- src/
|   +-- main.py                      # Entry point -- asyncio.run(main()); pygbag target
|   +-- assets/
|   |   +-- images/                  # Sprites, backgrounds, UI elements
|   |   +-- sounds/                  # SFX and music (OGG preferred)
|   |   +-- fonts/                   # TTF files
|   |   \-- data/                    # Static: sport configs, point value tables
|   |
|   +-- fanbidextrous/
|       +-- __init__.py
|       +-- settings.py              # SERVER_URL, screen size, FPS, colors, paths
|       +-- game.py                  # Top-level Game class -- owns the main loop
|       +-- states/
|       |   +-- __init__.py
|       |   +-- base_state.py
|       |   +-- sport_select.py      # Choose NHL or FIFA + pick today's game
|       |   +-- draft.py             # Pick screen -- alternating athlete selection
|       |   +-- watching.py          # Live game view -- HUD, waiting for next event
|       |   +-- event_reveal.py      # Animate a fired event; award points
|       |   \-- final_score.py       # End-of-game summary
|       |
|       +-- feed/
|       |   +-- __init__.py
|       |   +-- nhl_client.py        # Async HTTP: polls api-web.nhle.com/v1 directly
|       |   +-- fifa_client.py       # Async HTTP: polls api.balldontlie.io/fifa/v1 directly
|       |   +-- normalize.py         # Raw API JSON -> SportEvent (runs client-side)
|       |   \-- event_queue.py       # In-memory queue of unprocessed SportEvents
|       |
|       +-- sync/
|       |   +-- __init__.py
|       |   +-- relay_client.py      # GET/POST to drpeterjamieson.com/game/sync.php
|       |   \-- session.py           # SessionState: seed, window number, known picks
|       |
|       +-- ui/
|       |   +-- __init__.py
|       |   +-- hud.py               # Live score strip, period/half, clock
|       |   +-- athlete_card.py      # Renders a drafted athlete tile (name, team, position)
|       |   +-- draft_board.py       # Pick screen layout
|       |   +-- event_flash.py       # Animated event notification (GOAL!, PENALTY!, etc.)
|       |   \-- button.py
|       |
|       \-- models/
|           +-- __init__.py
|           +-- sport_event.py       # SportEvent (mirrors server normalize output)
|           +-- draft.py             # DraftPool, DraftedAthlete, DraftPick
|           +-- session.py           # GameSession: scores, picks, current state
|           \-- config.py
|
+-- tests/
|   +-- conftest.py
|   +-- fixtures/
|   |   +-- nhl_pbp_sample.json      # Captured NHL play-by-play response
|   |   +-- nhl_boxscore_sample.json # Captured NHL boxscore response
|   |   +-- fifa_events_sample.json  # Captured Balldontlie events response
|   |   \-- fifa_match_sample.json   # Captured Balldontlie match detail response
|   +-- test_normalize_nhl.py        # Raw NHL JSON -> SportEvent
|   +-- test_normalize_fifa.py       # Raw FIFA JSON -> SportEvent
|   +-- test_draft_pool_nhl.py       # Two-step NHL draft query against fixtures
|   +-- test_draft_pool_fifa.py      # Two-step FIFA draft query against fixtures
|   +-- test_scorer.py               # SportEvent x DraftPicks -> correct point deltas
|   +-- test_rng_sync.py             # Same seed + same athlete list -> identical shuffle on both clients
|   \-- test_relay_client.py         # relay_client GET/POST against a mock PHP response
|
+-- scripts/
|   +-- build_web.sh                 # pygbag --build src/
|   +-- run_server.sh                # Start cache server with chosen sport + game
|   +-- capture_fixtures.py          # Hit live APIs once, save JSON to tests/fixtures/
|   \-- validate_assets.py
|
+-- build/
|   \-- web/                         # pygbag output (gitignored)
|
\-- docs/
    +-- schema.md                    # SportEvent, DraftPool, DraftedAthlete, GameSession schemas
    +-- api-notes.md                 # NHL + FIFA field reference, gotchas, rate limit math
    +-- commands.md
    +-- log.md
    +-- game-design.md               # Point values, draft rules, event scoring table
    +-- art-style.md
    \-- superpowers/
        +-- specs/
        \-- plans/
```

---

## 9. Asset Conventions

All game assets live inside `src/assets/`. pygbag serves files relative to the build root.

**Images:** PNG. Athlete cards, team crests, event icons (goal flame, penalty whistle, etc.).

**Sounds:** OGG Vorbis. Pre-load in `on_enter()`. Key SFX: goal scored, card shown,
drafted athlete involved in event, points awarded, draft pick made.

**Fonts:** TTF. Load once, store in a module-level dict keyed by (name, size).

---

## 10. Architecture Highlights

**Draft -> Watch -> Score is the session lifecycle.** The state machine reflects this:
sport_select -> draft -> watching (loop: event_reveal -> watching) -> final_score.

**athlete_ids is the scoring bridge.** Every `SportEvent` carries a list of
`"{sport}-{player_id}"` strings. The server's `scorer.py` does one query:
`SELECT player_slot FROM draft_picks WHERE athlete_id IN (...)` and updates
`session_scores` for every match. Simple, fast, testable.

**Two-step draft query is pre-game only.** The FIFA 12-second sleep between match detail
requests is acceptable at draft-pool-build time (happens once, before the game). It is
NOT acceptable in the live event loop, which is why live events come from a different
endpoint (`/matches/{id}/events`) that can be polled at 120s without per-match sub-queries.

**Fixtures for deterministic tests.** `scripts/capture_fixtures.py` hits the live APIs once
and saves the raw JSON to `tests/fixtures/`. All normalize and draft-pool tests run against
these committed fixtures, never against live APIs. Updating fixtures is a deliberate act.

**No threading.** The pygame client is single-threaded (WASM constraint). The 120-second
feed poll runs as an `asyncio` coroutine sharing the main loop via `asyncio.ensure_future()`.
The server uses `asyncio` too; both polling loops are coroutines on the same event loop.

**dt-based timing.** All visual timers (event flash duration, countdown bars) multiply by
`dt` -- never assume a fixed frame rate.

---

## 11. Game Schema — Open Questions

### 11.1 Draft rules
- How many athletes does each player draft? (suggested: 5-8)
- Snake draft (A picks, B picks, B picks, A picks...) or simultaneous blind picks?
- Can both players pick the same athlete, or is each athlete exclusive once chosen?
- Is there a position requirement (e.g. must pick at least 1 goalie in NHL)?

### 11.2 Scoring model
- Base points per event type: goal = ?, penalty = ?, shot = ?, hit = ?
- NHL goal strength multipliers: power-play goal worth more? Empty-net worth less?
- FIFA own-goal: does it score for the owner, or count negative?
- Assist credit: does the `assist1PlayerId` score partial points?
- Timeout/no-event: is there a penalty for a quiet stretch, or just 0?

### 11.3 Prediction layer (optional v1 feature)
- Beyond drafting, do players also predict specific upcoming events each window?
- Or is v1 purely draft-based (athlete scores = player scores, no active prediction needed)?
- If predictions are added, do they layer on top of draft points or replace them?

### 11.4 Visual and audio conventions
- Target resolution: [FILL IN -- recommend 1280x720]
- Art style: [FILL IN]
- Athlete card design: show name + team + position + jersey number?
- Does the draft board show all athletes at once or paginated by team?

### 11.5 Session and connectivity model
- Two separate browsers on separate machines, joined by SESSION_CODE shared out-of-band.
- Player A creates session -> gets CODE -> texts it to Player B -> Player B enters CODE.
- **Settled:** PHP relay on drpeterjamieson.com is the only server-side component.
- **Open:** what happens if one client falls behind on polling (slow connection, tab backgrounded)?
  Options: (a) tolerate brief desync, reconcile on next relay poll; (b) add a "waiting for
  opponent" blocking screen whenever a window pick is missing from the relay.
- **Open:** session file cleanup -- PHP cron job deletes files older than 24h?

---

## 12. Build Phases

| Phase | Duration | Deliverable |
|---|---|---|
| 1 -- Foundation | 1 week | Scaffold, pygame-ce window, pygbag build succeeds, settings, asset loader, RELAY_URL constant |
| 2 -- Data Layer | 1 week | Two-step draft query for both sports (client-side); normalize to SportEvent; fixture capture script; normalize + draft pool tests |
| 3 -- PHP Relay | 1 week | sync.php written and deployed; relay_client.py GET/POST; session create/join flow; RNG seed exchange; rng_sync test passes |
| 4 -- Draft Screen | 1 week | Draft UI; athlete cards; RNG-ordered pool; picks POSTed to relay; poll for opponent pick before advancing |
| 5 -- Live Loop | 1 week | 120s event polling both sports; SportEvent scoring against local DraftPicks; window pick submission to relay |
| 6 -- Game UI | 1 week | HUD, event flash, watching state, window reveal, final score screen |
| 7 -- Polish | 1 week | SFX, art, fonts, error handling (no game today, API down, opponent pick timeout, relay unreachable) |
| 8 -- Deploy | 1 week | pygbag WASM on static host; php deployed; end-to-end test with two real browsers |

---

## 13. Deployment

**Game client:** pygbag static build -> GitHub Pages / Netlify / itch.io HTML5.
```
.venv/Scripts/python -m pygbag --build src/
# upload build/web/ to host
```

**Cache server:** runs continuously on a machine with internet access during a game session.
Players point their browsers at the same `SERVER_URL`.
```
cd server
python server.py --sport nhl --date 2026-06-05
# or
python server.py --sport fifa --date 2026-06-05
```

The cache server URL is set in `src/fanbidextrous/settings.py` as `SERVER_URL`.
Local dev: `http://localhost:8080`. Production: VPS address or home server with port-forwarding.

---

## 14. Testing Strategy

- **Fixture tests** (`test_normalize_*.py`, `test_draft_pool_*.py`): all run against committed
  JSON in `tests/fixtures/` -- never hit live APIs. `capture_fixtures.py` refreshes them.
- **Scorer tests** (`test_scorer.py`): given a `SportEvent` and a `draft_picks` table,
  assert correct point deltas for every event type. Covers edge cases: own goals, multi-player
  events (scorer + assists all owned by same player), events with no drafted athlete.
- **Cache DB tests** (`test_cache_db.py`): dedup by `event_id`, `since` query returns only
  new rows, score updates are atomic.
- **Model round-trips** (`test_models.py`): every Pydantic model serializes and deserializes
  cleanly; unknown fields dropped without error (forward compat for API changes).

---

## 15. Relationship to Other Tools

This project is standalone. It does not depend on the Hockey Drill Designer, the Curriculum
Generator, or the Sports Analytics Tool.

---

*Document version: 0.4 -- PHP relay replaces cache server; RNG seed sync contract defined;
client-side normalize; relay JSON format specified; no Python backend process required.*
