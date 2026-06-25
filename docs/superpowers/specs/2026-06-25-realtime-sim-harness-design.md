# Realtime Sim Harness -- Design

Date: 2026-06-25
Status: APPROVED (pending spec review)

## Goal

Let the developer ("drpaj") rehearse the LIVE dungeon flow end to end with NO real
match -- choosing where they "arrive" relative to kickoff (-5 = five minutes before
kickoff, +5 = five minutes after, +20 = mid-W1 at the 20th minute) -- while the live
logic runs byte-identically and an on-screen `[drpaj]` diagnostic trail records every
API/local query and clock decision and WHEN it happened.

This exists to exercise (and regression-check) the late-join catch-up, predict-deadline
defaulting, force-resolve, and data-ready gate that the 2026-06-24 bug-fix touched --
without waiting on a real fixture.

## Core principle: reuse the live path, do not fork it

The LIVE dungeon path (`DungeonPartyFlow` driven by `start_dungeon_party_live`) is
driven by exactly two external inputs:

1. The wall clock -- `time.time()` feeding `MatchClock(kickoff_epoch, HalfClock)`.
2. The feed -- `feed_client.get_feed(fixture_id)` recorded into a `LiveFeed`, whose
   `last_known_minute()` / `snapshot_at()` drive catch-up and resolution.

The harness swaps ONLY those two inputs. Game logic, screens, catch-up, defaulting,
force-resolve, and the data-ready gate are untouched and shared. When no clock source
and no sim feed are attached, the production live path runs exactly as today.

## Seam 1 -- Clock source

`DungeonPartyFlow` currently calls `time.time()` at 9 sites. Introduce one private
accessor:

```python
def _now(self) -> float:
    return self.clock_source.now(time.time()) if self.clock_source else time.time()
```

Replace every `time.time()` inside the flow's live arithmetic with `self._now()`.
`clock_source` defaults to `None` (production live = plain `time.time()`).

### `src/game/sim_clock.py` (NEW, pure, no pygame)

```python
@dataclass
class SimClock:
    virtual_start: float   # virtual epoch at harness start
    real_start: float      # real epoch captured at harness start
    rate: float = 1.0      # 1.0 = realtime 1:1 ; 0.0 = manual/stepped
    manual_seconds: float = 0.0

    def now(self, real_now: float) -> float:
        if self.rate == 0.0:                       # accelerated / stepped
            return self.virtual_start + self.manual_seconds
        return self.virtual_start + (real_now - self.real_start) * self.rate

    def step(self, seconds: float) -> None:        # the "skip forward" action
        self.manual_seconds += seconds
```

Kickoff is positioned from the chosen offset (NOT stored in SimClock -- it sets
`flow.kickoff_epoch` like the live path does):

```
kickoff_epoch = virtual_start - offset_minutes * 60
  offset +20 -> kickoff 20' in the past -> current_minute == 20 at start (mid-W1)
  offset  -5 -> kickoff 5' in the future -> pre-game (playing_window 0, editing 1)
```

### Speed modes

- **Realtime** (`rate = 1.0`): true 1:1. A 15-minute window takes 15 real minutes --
  exact production cadence, including the poll rhythm.
- **Accelerated** (`rate = 0.0`): the virtual clock advances only when stepped. Stepping
  reuses the EXISTING SIM hotkeys (`src/ui/sim.py`): in stepped mode the `F`
  ("fast-forward this window") hotkey advances the virtual clock to the next window
  boundary via `SimClock.step(...)`, so the real force-resolve / boundary path fires
  through the unchanged logic -- it is NOT the old auto-pick-to-resolution shortcut.
  `S` (skip/continue) keeps its existing meaning on recap/continue screens.

## Seam 2 -- Sim feed

### `src/game/sim_live_feed.py` (NEW, pure, no pygame)

`SimLiveFeed` presents a recorded StatsBomb match (an existing `ReplayFeed`) through the
`LiveFeed` interface the flow consumes, but its visible progress is governed by the
virtual clock so the feed "lags" exactly like the real one:

- `last_known_minute()` -> the virtual clock's current ABSOLUTE match minute, clamped to
  the recording's final minute (so the feed never reports data it would not yet have).
- `snapshot_at(minute)` -> delegates to the `ReplayFeed` (cumulative StatsBomb stats).
- `match_status()` / `match_status_at(minute)` -> derived from the minute + recording
  meta (1H / HT / 2H / FT), using the same status constants as live.
- `current_minute()`, `home_team/away_team/home_goals/away_goals`, `kickoff_iso()`,
  `seed_kickoff()`, `has_lineups()`, `lineups()` -> from the recording / a seeded kickoff.
- `record(snapshot)` -> no-op (progress comes from the clock, not pushed snapshots).

It needs a reference to the same `SimClock` + kickoff_epoch so it can convert "now" to a
match minute. To stay pure, it takes a zero-arg `minute_now: Callable[[], int]` injected
by the flow (the flow already knows kickoff_epoch and `_now()`).

### `src/sync/sim_feed_client.py` (NEW)

`SimFeedClient` matches the `FeedClient` surface the flow calls (`get_feed`,
`get_live_fixtures`, `is_lead`, `transport_name`). `get_feed(fixture_id)` is the single
"API QUERY" point: it writes a `[drpaj] QUERY get_feed(...)` diagnostic line (see below)
and returns the current `SimLiveFeed` snapshot. No network, no relay.

## Logging -- `src/game/diag_log.py` (NEW, pure) into the existing scrollable panel

`PartyPlayScreen` ALREADY owns a scrollable `LogList` (+ `ScrollButtons` gutter) where
the crawl results post and which it drains from the coordinator log each frame. The
diagnostic trail rides the same panel.

Each line carries an ACTOR tag so a co-op run shows BOTH sides in one timeline -- what
this client did AND what the other client did, each stamped with the time it happened
(observed). The lead client's tag is its username (`drpaj`); the other player's lines are
tagged with the peer's username (or `peer` if unknown).

```python
class DiagLog:
    def __init__(self, enabled: bool, actor: str) -> None: ...   # actor = this client's tag
    def add(self, minute: int, kind: str, detail: str) -> None:
        # local action: "[<actor>] t=+MM:SS min=NN' KIND detail"
    def add_peer(self, peer: str, minute: int, kind: str, detail: str) -> None:
        # observed peer action: "[<peer>] t=+MM:SS min=NN' KIND detail"
    def drain(self) -> list[str]:
        # returns + clears lines not yet shown (screen appends them to its LogList)
```

The flow holds one `DiagLog`, writes at each meaningful point, and the play screen drains
new lines into its `LogList` every frame (same mechanism it uses for the crawl log).
Lines are ASCII-only (project rule). Example trace from the LEAD device's panel in a co-op
arrive-at-+20 realtime run (its own `[drpaj]` lines interleaved with observed `[ally]`):

```
[drpaj] t=+20:00 min=20' KICKOFF set offset=+20 (arrive mid-W1)
[drpaj] t=+20:00 min=20' QUERY get_feed(fixture=FRA-CRO) -> lkm=20' status=1H
[drpaj] t=+20:00 min=20' CATCH-UP target=1 (W1 deadline passed -> default, land W2)
[drpaj] t=+20:05 min=20' SHARE bundle W1 -> relay (default picks)
[ally]  t=+20:18 min=20' JOINED session, syncing seed+pool from blob
[drpaj] t=+25:00 min=25' W2 force_resolve (editing 2->3) data_ready=yes
[drpaj] t=+25:01 min=25' SHARE bundle W2 -> relay
[ally]  t=+25:14 min=25' bundle W2 OBSERVED in blob (ally can now resolve W2)
[drpaj] t=+45:00 min=45' W3 (extra-time absorber) resolve at whistle
```

The FOLLOWER device's panel is the mirror: its own actions tagged `[ally]`, and the
lead's bundle writes observed from the blob tagged `[drpaj]`. Because the two devices are
separate processes, "what the other one is doing" is surfaced from the shared relay blob
(bundles present, picks seen, join/seed sync) -- each client logs the peer events it can
observe, stamped with its own local sim time, so the panel reads as one combined timeline.

Diagnostic write points (local): kickoff/offset set; each `get_feed` query (minute +
resulting last_known_minute + status); catch-up target chosen (with the reason); each
force_resolve (which window, editing transition, data_ready); each window resolve
(data-ready vs default); bundle SHARE to relay; half re-anchor; reaching recap/final.
Peer write points (observed from blob each poll): peer join / seed+pool sync; peer bundle
for window W first OBSERVED; peer pick seen.

## Selection flow

New launcher entry **"SIM (realtime test)"** (config-labelled, alongside the existing
three modes). The picker chain:

1. **Mode**: Realtime vs Accelerated (small two-option screen, reuse `LauncherScreen`).
2. **Match**: the existing `SimGameSelectScreen` (FRA-CRO etc.).
3. **Offset**: a new lightweight `+ / -` selector screen -- starts at 0, `+`/`-` adjust by
   1', shows the current arrival ("arrive at +20' -- mid W1" / "-5' -- pre-game"), then
   START.

START calls the EXISTING `start_dungeon_party_live(...)` with the clock source + sim feed
+ DiagLog attached, instead of the real `FeedClient` / `LiveFeed` / fixture picker.

## Scope -- both phases in one plan

### Phase 1 -- Solo (`solo=True`)
Drives the party-of-one live dungeon path -- the one carrying the late-join/catch-up
logic. Reproduces and regression-checks all three 2026-06-24 playtest bugs.

### Phase 2 -- Co-op (two REAL devices over the real relay)
Co-op runs as TWO SEPARATE app instances -- e.g. a phone and a desktop -- NOT one
process. Each device independently runs the sim harness (`peer=True`) wired to the REAL
PHP relay (`RelayClient`), exactly like production peer-computed co-op, but with the sim
feed + sim clock in place of the live feed:

- Both players choose "SIM (realtime test)" -> Co-op, and enter the SAME session code
  (shared out-of-band, like real co-op). The api-lead (`drpaj`) also picks the match +
  offset; the follower just joins.
- The api-lead's `SimLiveFeed` + `SimClock` drive bundle production at sim-realtime pace;
  bundles + the creator-set seed flow through the real relay. The follower reads them and
  replays them locally -- its data-ready gate / catch-up track the lead's bundles
  arriving over (real) time, faithfully reproducing the live follower experience.
- This uses the EXISTING relay schema (seed + per-window `window_actuals` bundles) -- no
  PHP change. The only difference from live co-op is the feed source.
- Each device shows its own combined `[<self>]`/`[<peer>]` log panel (see Logging), so
  the relay handshake is visible from both phone and desktop.

Determinism across devices comes from the shared seed + identical bundles (the follower
never re-derives anything from the feed). The match + offset only need to match on the
lead, since the follower is bundle-driven.

## What stays untouched

- Production `LiveFlow` and the real `FeedClient` are never branched.
- With no clock source / sim feed attached, `_now()` is `time.time()` and the live API
  path is byte-identical to today.
- `src/game/` stays pygame-free; `SimClock`, `SimLiveFeed`, `DiagLog` are unit-tested in
  `tests/`. The sim feed client lives in `src/sync/` alongside `FeedClient`.

## Testing

- `tests/test_sim_clock.py` -- realtime advance, manual step, kickoff offset both signs,
  rate boundaries.
- `tests/test_sim_live_feed.py` -- last_known_minute tracks the clock and clamps at match
  end; snapshot_at delegates; status transitions 1H/HT/2H/FT by minute.
- `tests/test_diag_log.py` -- formatting (ASCII, t=+MM:SS, min stamp), drain semantics,
  disabled = no-op.
- A headless harness driver (extend `TOOLS/smoke_flow.py` or a new `TOOLS/smoke_sim_*`)
  that runs an offset=+20 solo realtime/stepped pass and asserts it lands on W2 (W1
  defaulted), W3 absorbs extra time, and it reaches the recap/final -- the three bugs.
- Co-op: shipped path is the REAL relay (two devices), which is verified by a manual
  phone+desktop run (documented procedure). For an AUTOMATED regression of the
  peer-bundle exchange, a test harness may wire two flows to an in-process `LocalRelay`
  (test-only) and assert the follower's bundle-driven catch-up + the combined
  `[self]`/`[peer]` log timeline -- the in-process relay is a test substitute, not the
  shipped co-op transport.
- Existing 363 tests must stay green (no live-path behavior change).

## Non-goals

- No new sports data; reuses bundled StatsBomb recordings.
- No change to the PHP relay schema (co-op reuses the existing seed + `window_actuals`
  bundle schema over the real `RelayClient`).
- Solo realtime/stepped is primarily a desktop dev tool; co-op spans phone + desktop (the
  follower device path must therefore work under pygbag/WASM like production co-op).
