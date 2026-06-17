# Mobile-Web UI Design

Date: 2026-06-16
Status: Approved for planning

## Goal

Build the complete mobile-web UI for the cooperative soccer prediction game as a
single end-to-end flow, locally testable with SIM acceleration (hotkeys). Same
dark/cyan generic theme. Pure-Python game logic stays separated from all pygame
rendering, per the golden rule.

## Locked design decisions (from the user)

- 1a (modified): cinematic event reveal has real STRUCTURE (tick events, meters
  fill and "explode" at threshold, shot taken, GOAL flash + shake, skippable) but
  rendered with SIMPLE primitives (rects/circles/text) -- graphics undecided.
- 2a: build the whole flow now, keep the same dark/cyan generic theme.
- 3b (modified): mobile-focused; TAP a card to SELECT it and zoom to a detail
  view; a dedicated "Select" button confirms the draft pick.
- 4b (modified): SIM controls are HOTKEYS only (no on-screen SIM bar) PLUS a
  popup that reminds the player of the hotkeys when SIM mode is on.
- Whole flow in one build (user chose option 1).
- Mobile-focused throughout (user emphasis).

## Mobile-first constraints (apply to every screen)

- Fixed portrait canvas 414 x 896 (config display.width/height). Single column.
- Touch, not hover: all interaction is tap. No hover-only affordances.
- Touch targets >= 44 px tall. Primary action button bottom-anchored (thumb reach),
  full-width minus side margins.
- Lists scroll by touch drag (and mouse wheel for desktop testing); momentum not
  required for v1.
- Fonts large enough to read on a phone: title >= 30 px, body >= 20 px, never below
  16 px. Sizes come from layout_config.json so they can be tuned.
- One primary action visible at a time; secondary actions smaller / above.

## Architecture

Reuses the reference project's two proven patterns:

1. Config-driven layout. New `config/layout_config.json` holds every rect, size,
   and font value as a named key with a default (prefixed per screen: `splash_*`,
   `room_*`, `draft_*`, `play_*`, `cine_*`, `final_*`, plus shared `ui_*`). A new
   `Layout` helper in `src/utils/constants.py` loads it once and exposes
   `LAYOUT.param(key, default)`. No magic numbers in UI code.

2. Time-driven animation state machine (from `roll_display.py`): the cinematic is
   a widget with `update(dt)`, `draw(surface)`, `skip()`, `is_done`, advancing
   through timed states. The *data* it animates (event order, per-tick meter
   values, threshold crossings, shot/goal beats) is computed in pure Python.

### Module layout

Pure game logic (zero pygame, unit-tested in tests/):
- `src/game/cinematic.py` (NEW) -- `build_cinematic_script(window_result, actuals,
  meters_before, meters_after, threshold)` returns a `CinematicScript`: an ordered
  list of beats (TICK with meter values, EXPLODE when a meter crosses threshold,
  SHOT, GOAL/CONCEDE/MISS). Deterministic, fully testable.

UI / pygame (src/ui/):
- `src/ui/flow.py` (NEW) -- flow controller. Owns the App-level state machine and
  SIM mode. Replaces demo_flow's nested-callback chain. Sequence:
  Splash -> Room -> Draft(team A) -> Draft(team B) -> Play loop -> Final.
- `src/ui/sim.py` (NEW) -- SIM mode object: enabled flag, hotkey handlers, the
  help-popup state. Hotkeys: S skip/advance, A auto-pick prediction, R auto-draft 6,
  F fast-forward window, H toggle help popup.
- `src/ui/screens/splash.py` (NEW) -- loading: title + dots + cycling tips +
  progress bar; dt-based; auto-advances (instant in SIM).
- `src/ui/screens/room.py` (NEW) -- Create Room / Join Room (code entry). SIM mode
  auto-creates "SIM01" and proceeds; shows the hotkey popup on entry.
- `src/ui/screens/draft_screen.py` (REWORK) -- scrollable pool; tap a card to
  SELECT+zoom into a detail panel; "Select" button confirms into roster; "Lock
  Roster" enabled at roster_size. Runs once per team.
- `src/ui/screens/play_screen.py` (NEW, absorbs predict) -- top: window # +
  countdown timer; middle: scrollable result/prediction log; bottom: prediction
  stat-steppers (reuse predict_screen logic) + "Lock Predictions".
- `src/ui/screens/cinematic_screen.py` (NEW) -- renders a CinematicScript via the
  animation widget; tap or S to skip; on finish, appends to the log and continues.
- `src/ui/screens/final_screen.py` (REWORK of status_screens.FinalScreen).
- `src/ui/widgets.py` (EXTEND) -- add `MeterBar` explode state, `PlayerDetail`
  zoom panel, `Popup`, `LogList`, `CountdownTimer` label.

Config:
- `config/layout_config.json` (NEW) + `Layout` in `src/utils/constants.py`.

Dev tooling (TOOLS/, never in the pygbag build):
- `TOOLS/ui_tweaker.py` (NEW) -- slim mobile tweaker: live 414x896 portrait preview
  (left) of a chosen screen against synthetic state + slider/value panel (right)
  editing `layout_config.json`; Ctrl+S save, R reload, arrow-nudge selected value,
  click a row to select, screen picker buttons. Mirrors `ui_tweaker_mobile.py`.

## Data flow

1. App starts -> flow.start(app, sim_mode). flow shows Splash.
2. Splash done -> Room. SIM auto-creates and advances; popup reminds of hotkeys.
3. Room done -> Draft team A -> Draft team B. Each draft confirms picks via the
   Select button, locks at roster_size (6). Builds two Rosters from the shared pool.
4. Play loop per window: PlayScreen collects predictions -> session.resolve_window
   -> build_cinematic_script(...) -> CinematicScreen animates it -> append summary
   to the log -> next window, until feed.match_status finished -> FinalScreen.
5. SIM hotkeys short-circuit user input at each step (auto-draft, auto-pick, skip,
   fast-forward).

The existing engine (GameSession, Roster, scoring, ReplayFeed, MockFeed,
actuals_from_raw) is unchanged. The cinematic reads the same per-window actuals and
ScoreEvents already produced by resolve_window.

## Cinematic structure (simple primitives)

Beats, in order, driven by the window's real event deltas:
- For each stat that changed (corner, shot, save, card): a TICK beat that nudges
  the relevant meter bar up by the predicted/actual contribution; bar animates fill.
- When a meter reaches threshold (6): EXPLODE beat -- bar flashes, briefly scales
  up, particle-like radial lines (drawn primitives), meter resets visually.
- SHOT beat: a "SHOT!" label + a circle traveling toward a goal rectangle.
- Resolution beat: GOAL -> full-screen cyan/white flash + screen shake + big
  "GOALLLLL!!!" text; CONCEDE -> red flash + "CONCEDED"; MISS -> dim "no goal".
- Skippable at any time (tap or S): jumps to DONE showing the final meter state and
  outcome text.

All rendering is rectangles, circles, lines, and text in theme colors. No assets.

## SIM mode (hotkeys + reminder popup)

- Enabled by `src/main.py --sim <slug>` (already parsed) or a `--simdemo` flag for
  the MockFeed path. flow passes sim_mode into every screen.
- Hotkeys (handled centrally in sim.py, screens query it):
  - H: toggle the hotkey help popup (also auto-shown once on Room entry).
  - R: on a Draft screen, auto-select 6 valid players and lock.
  - A: on a Play screen, auto-fill a valid prediction set and lock.
  - S: skip the current cinematic / advance splash.
  - F: fast-forward -- run the current window with an auto prediction straight to
    the cinematic.
- The popup is a centered panel listing the hotkeys; tap or H dismisses it.

## Testing

- Pure: `tests/test_cinematic.py` -- script ordering, EXPLODE on threshold cross,
  SHOT/GOAL/CONCEDE/MISS beats from sample window results, skip => DONE state.
- Existing 52 tests must stay green (engine untouched).
- Manual gate: `python src/main.py --sim wc2018_final_fra_cro` walks the full flow;
  pygbag mobile build still builds. (Browser smoke test remains manual gate A2.)

## Out of scope (unchanged deferred work)

C1 live two-player loop, C2 live feed, C3 opponent-mode UI, C4 audio/art polish,
C5 NHL adapter. This build is single-device against MockFeed / ReplayFeed, which is
exactly what the SIM flow needs.
