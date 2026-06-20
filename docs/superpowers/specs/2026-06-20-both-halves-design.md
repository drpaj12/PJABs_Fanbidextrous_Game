# Both-Halves Live Play -- Design Spec

> Date: 2026-06-20
> Status: approved (brainstorming), ready for implementation plan

## Problem

Today "Live" only ever plays the **first half**. If a player opens the game during
half-time or the second half, `live_plan` reports "first half already over" and drops
them on a dead-end FinalScreen. We want Live to support **both halves**, auto-selecting
which one the player joins based on the wall-clock state of the real match at join time.

Original ask (verbatim): *"when you choose live, it picks which half of the soccer match
you're playing in. Therefore, it's both halves. You can come in late in first half
(before half way through) otherwise, you are pushed to the next half game."*

## Decisions (all approved)

- **Each half is a SEPARATE game.** Its own draft, its own `GameSession`, its own meters,
  its own FinalScreen. There is no aggregate-across-both score.
- **The half is auto-selected by join time** (the player never picks a half explicitly).
- **Join cutoff = the half's midpoint** (config `live.join_cutoff_minute`, default 22 =
  `half_minutes // 2`). Join before the cutoff → play that half. After → pushed forward.
- **Too late for the first half → pushed to the second-half game** (a wait screen if the
  2H has not kicked off yet).
- **No half left** (past the 2H midpoint, or full-time) → a short notice → back to the
  Live pick screen (`FixtureSelectScreen`).
- **Second-half wall-clock anchor is an API-derived estimate, then self-corrects.** We
  cannot know the real 2H kickoff instant, so we estimate it and **re-align on every poll**
  if the estimate drifts more than a threshold (config `live.resync_threshold_seconds`,
  default 30s). Re-alignment is generalized to BOTH halves (the 1H anchor from config
  kickoff is also just an initial estimate that self-corrects).
- **Persistent on-screen label of which game you're in** ("First Half" / "Second Half"),
  shown the whole time you play, plus the soccer-style minute (46'-90' in the 2H).

---

## A. Join decision table (`half_picker`, pure)

New pure module `src/game/half_picker.py`. Decides, from the live state at join time,
which half to play (or none). Uses the **raw API status short code** (`feed.status_short()`)
because we must distinguish `1H` / `HT` / `2H` / `FT`, which the mapped engine status
(`live` / `halftime` / `finished`) collapses.

```
HalfChoice(half: Optional[int], needs_wait: bool)
    half       1, 2, or None (no playable half remains)
    needs_wait True only when half == 2 but the 2H has not started yet (status 1H-late/HT)

pick_half(status_short, elapsed, half_minutes, join_cutoff_minute) -> HalfChoice
```

| status_short        | condition                              | result                  |
|---------------------|----------------------------------------|-------------------------|
| NS / TBD / PST      | pre-match                              | `HalfChoice(1, False)`  |
| 1H                  | `elapsed < join_cutoff_minute`         | `HalfChoice(1, False)`  |
| 1H                  | `elapsed >= join_cutoff_minute`        | `HalfChoice(2, True)`   |
| HT                  | half-time                              | `HalfChoice(2, True)`   |
| 2H                  | `elapsed - half_minutes < cutoff`      | `HalfChoice(2, False)`  |
| 2H                  | `elapsed - half_minutes >= cutoff`     | `HalfChoice(None,False)`|
| ET / BT / P         | extra time / break before ET / pens    | `HalfChoice(None,False)`|
| FT/AET/PEN/ABD/...  | finished                               | `HalfChoice(None,False)`|
| unknown             | (defensive)                            | `HalfChoice(None,False)`|

`elapsed` is the API match minute (`feed.current_minute()`, 1-90+). `join_cutoff_minute`
is **half-relative** (22), so the 2H test subtracts `half_minutes` first.

---

## B. Wall-clock anchor + re-alignment

### Initial anchor (caller computes, per half)
- **1H:** `kickoff_epoch = now + seconds_to_kickoff(feed.kickoff_iso(), now)` (config
  kickoff, as today). If unknown, `now`.
- **2H:** `kickoff_epoch = now - (api_minute_in_half) * 60`, where
  `api_minute_in_half = max(0, feed.current_minute() - half_minutes)`. This is an
  estimate (integer-minute granularity + API lag); it is corrected by re-alignment.

### Re-alignment (`MatchClock.realign`, pure)
`MatchClock` is frozen; `realign` returns a new instance (or `self` if within threshold).

```
realign(api_minute_in_half: int, now: float, threshold_seconds: float) -> MatchClock
    our_elapsed = now - self.kickoff_epoch                 # seconds since our anchor
    api_elapsed = (api_minute_in_half + 0.5) * 60          # midpoint of the integer minute
    if abs(our_elapsed - api_elapsed) > threshold_seconds:
        return MatchClock(now - api_elapsed, self.clock)   # snap anchor to API
    return self
```

Called once per frame in `LivePlayScreen.update` (only when the feed is live and has a
minute > 0), so each fresh poll's API minute nudges the wall clock back into line. It
applies to both halves: the 1H config-kickoff anchor self-corrects too.

### Re-alignment safety (high-water mark)
Re-alignment can move the anchor backward (when we were running ahead). To guarantee a
backward correction never re-locks an already-played window, the screen detects newly
entered windows with a **monotonic high-water mark** instead of a frame-delta:

```
# pure helper in live_play_screen.py
windows_to_enter(max_entered: int, playing_window: int) -> list[int]
    return list(range(max_entered + 1, playing_window + 1))
```

Each frame: `cur = mc.playing_window(now)`; lock/queue every window in
`windows_to_enter(self._max_entered, cur)`; then `self._max_entered = max(self._max_entered, cur)`.
A forward correction (we were behind) catches up missed windows via the SAME path the
focus-loss case already uses; a backward correction yields an empty list (no rewind).
`self._max_entered` initializes to `editing_window_start - 1`. This replaces the existing
`MatchClock.windows_entered(prev_now, now)` call in the screen (the `MatchClock` method
stays for its own tests; the screen no longer tracks `self._last_now`).

---

## C. Half model (absolute match minutes)

`HalfClock` gains a `start_minute` offset so window boundaries are **absolute match
minutes** (what the cumulative-stats feed is indexed by):

```
@dataclass(frozen=True)
class HalfClock:
    half_minutes: int
    window_minutes: int
    start_minute: int = 0          # 0 for 1H, 45 for 2H

    window_start(w) = start_minute + (w - 1) * window_minutes
    window_end(w)   = start_minute + w * window_minutes
    # regular_windows, extra_time_window, is_extra_time, is_half_over: UNCHANGED
```

- 1H: `start_minute=0` -> window_start/end identical to today (0..45, ET at 45).
- 2H: `start_minute=45` -> windows cover 45..90, ET window_start = 90.

Window **indices** stay 1-based per half (1..9 + ET=10) for both halves; only the
start/end minute values shift. `LiveFlow._window_actuals_for` already calls
`clock.window_start/window_end`, so 2H actuals automatically read the correct absolute
slice (`snapshot_at(abs_end) - snapshot_at(abs_start)`).

`MatchClock.current_minute(now)` stays **half-relative** (0..45, minutes since this half's
anchor) so `playing_window` / `editing_window` work unchanged for both halves. A new
display helper exposes the absolute minute for the header:

```
MatchClock.display_minute(now) = self.clock.start_minute + self.current_minute(now)
```

---

## D. Flow & screens

### `start_live` (rewired)
1. Build `LiveFeed`, seed kickoff, warm cache, build `FeedClient`/`SimMode` (unchanged).
2. `LiveWaitScreen(wait_for_lineups=True, on_ready=after_lineups)` (unchanged gate).
3. `after_lineups()`:
   - `choice = pick_half(feed.status_short(), feed.current_minute(), HALF_MIN, JOIN_CUTOFF)`
   - `choice.half is None` -> `RevealScreen(["This match has no half left to play.",
     "Pick another match."], on_continue=back_to_picker)` where `back_to_picker` calls
     `start_live_select(...)`.
   - `choice.needs_wait` -> `LiveWaitScreen(wait_for_second_half=True,
     on_ready=lambda: launch_half(2))`.
   - else -> `launch_half(choice.half)`.
4. `launch_half(half)`:
   - `clock = HalfClock(HALF_MIN, WINDOW_MIN, start_minute=0 if half==1 else HALF_MIN)`
   - `kickoff_epoch` per section B.
   - Defensive gate: `plan = live_plan(elapsed_in_half, feed.match_status(), clock)`; if
     `not plan.scored_windows` -> the same "no half left" notice -> picker.
     (`elapsed_in_half = max(0, feed.current_minute() - clock.start_minute)`.)
   - `LiveFlow(app, feed, feed_client, fixture_id, pool, half, clock, kickoff_epoch,
     sim, on_snapshot=persist).start()`.

### `LiveWaitScreen` -- new `wait_for_second_half` mode
- New param `wait_for_second_half: bool = False`.
- `_is_ready()` gains a branch: when `wait_for_second_half`, ready once
  `feed.status_short().upper() == "2H"` **or** `feed.match_status() == "finished"`
  (match ended during the break -> `launch_half(2)`'s gate then sends them to the picker).
- Label: "Second half starts soon...". Polling already continuous for non-lineup waits
  (`_should_poll` returns True when `not wait_for_lineups`), so no change there.

### `LiveFlow` -- half-aware
- New constructor: `LiveFlow(app, feed, feed_client, fixture_id, pool, half, clock,
  kickoff_epoch, sim, on_snapshot=None)`. Drops the `plan` param (its `_scored` was dead);
  `self.clock = clock` (half-aware), `self.half = half`, `self.kickoff_epoch = kickoff_epoch`,
  `self.half_label = SECOND_HALF_LABEL if half==2 else HALF_LABEL`.
- `_after_draft`: build session, `MatchClock(self.kickoff_epoch, self.clock)`,
  `editing_start = match_clock.editing_window(now)`, construct `LivePlayScreen` passing the
  new `half_label` and `resync_threshold_seconds`. (No more local `seconds_to_kickoff`
  recompute -- the caller fixed the anchor.)
- `_fixture`: `label = self.half_label`.
- `_to_final`: `FinalScreen(app, team, opp, None, on_continue=back_to_picker,
  title=HALFTIME_LABEL if half==1 else FULLTIME_LABEL)` where `back_to_picker` ->
  `start_live_select(...)` so the player can then pick the same match's other half (or
  another match).

### `LivePlayScreen` -- label, minute, re-align
- New params `half_label: str` and `resync_threshold_seconds: float`.
- Header: draw `half_label` persistently (top strip), and use `mc.display_minute(now)`
  for the clock (so the 2H shows 46'-90').
- `update()`: after the poll trigger, re-align (section B) when live with minute > 0; then
  detect entered windows via the high-water mark (`windows_to_enter`), replacing the
  `windows_entered` / `_last_now` mechanism. Lock/queue/drain/halftime logic otherwise
  unchanged (the deferral-gate `windows_ready` stays as-is).

---

## E. Config

`config/game_config.json`:
- `live.join_cutoff_minute`: `22` (half-relative; pushed forward at/after this minute).
- `live.resync_threshold_seconds`: `30` (re-align snap threshold).
- `game.second_half_label`: `"Second Half"`.
- `game.fulltime_label`: `"Full Time"`.

Per-fixture `kickoff` stays the **1H** estimate; there is no 2H config (it is API-derived).

**v1 limitation (documented, not fixed here):** the 2H draft pool comes from the same
starting-XI lineups the API published pre-match (`_pool_from_feed`); substitutions made
during the match are not reflected. Acceptable for v1.

---

## F. Testing

Pure unit tests (no pygame), per the golden rule:
- `tests/test_half_picker.py`: every row of the section-A table.
- `tests/test_half_clock.py` (extend): `start_minute` offset on window_start/window_end
  for 1H (0) and 2H (45); ET window_start = 90 for 2H.
- `tests/test_match_clock.py` (extend): `realign` snaps when drift > threshold, no-ops
  within threshold, and the returned clock's `current_minute` matches the API minute;
  `display_minute` applies the offset.
- `tests/test_live_play_screen_logic.py` (extend): `windows_to_enter` high-water behavior
  (forward catch-up, backward no-rewind).
- `tests/test_live_schedule.py` (extend): `live_plan` with half-relative elapsed for the
  2H yields the expected scored windows.

Headless integration:
- `TOOLS/smoke_flow.py` (extend): a `live_smoke_2h()` driving a `start_minute=45` clock
  with an injected `now_fn` and a feed reporting `2H` then `FT`, asserting 2H windows lock,
  re-alignment keeps the clock honest, and `on_finished` fires. ASCII output, non-zero
  exit on FAIL.

All existing suites must stay green (`.venv/Scripts/python -m pytest tests/`), the game
must still launch (`.venv/Scripts/python src/main.py`), and `log.md` gets one line per
increment.
