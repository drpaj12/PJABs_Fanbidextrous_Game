# Player Insight + Live-Game Polish -- Design

Date: 2026-06-20

## Goal

Address a seven-item UX punch list, in two themes that ship together in one build:

- **Player insight (#4-#7):** surface each drafted athlete's abilities -- a richer
  tap-to-zoom detail panel reused identically on the draft screen AND the live/offline
  over-under + pick-player screens; tap-anywhere-to-dismiss (except Select); an ability
  tagline on the draft cards.
- **Live-game navigation/display (#1-#3):** three-letter team codes so fixture titles
  fit; a wall-clock kickoff countdown after a game is picked; a back button on the lobby.

## Architecture

The golden rule holds: all human-readable ability text comes from one new **pure,
zero-pygame, fully tested** module, `src/game/ability_text.py`. The UI layer (widgets +
screens) consumes it. Phrasing lives in `assets/data/powers.json` (new `blurbs` and
`effect_phrasing` blocks), so no English strings are hardcoded in `.py`. All new geometry
lives in `config/layout_config.json`.

## Components

### 1. `src/game/ability_text.py` (new, pure)

Turns a `DraftedAthlete` into plain English by reading the resolved effects from
`powers.py` (`this_window_effect`, `next_window_effect`, `conversion_for`) and the phrasing
templates from `powers.json`.

- `role_summary(athlete) -> str` -- one-line role read; returns the archetype's `blurb`
  (fallback: the archetype code).
- `effect_lines(athlete) -> list[str]` -- e.g.
  `["This window: +32% shot conversion", "Next window: +2.4 concede risk",
    "Shot conversion: 50%", "Rating: *****"]`.
- `card_tagline(athlete) -> str` -- the compact this-window effect phrase (no prefix),
  for the draft card third line.

Number formatting helpers map an effect `value` to `{signed}` (`+1.0`/`-0.8`),
`{mult}` (`3.2`), `{pct}` (`+32%`); each `kind` template in `effect_phrasing` chooses which.
Stars render as ASCII `*` (matches existing widgets; pygbag default font has no star glyph).

### 2. `powers.json` additions

`blurbs`: one short ASCII role line per archetype (GK..ST).
`effect_phrasing`: one template per effect `kind`:
`negate_concede_shot`, `success_credit_add`, `success_credit_mult`,
`concede_credit_add`, `concede_credit_mult`, `conversion_add`.

### 3. `PlayerDetail` (widgets.py) -- richer zoom panel (#6)

Below name, render the `role_summary` (word-wrapped, accent), a compact info block
(Position / Team / Jersey), then an "Abilities" header and the `effect_lines`. Select
button stays pinned. New helper `wrap_text(text, font, max_w) -> list[str]` in widgets.

### 4. `athlete_card` (widgets.py) -- ability tagline (#4)

New optional `tagline: str = ""` param. When present, draw a third muted small line.
Only the draft screen passes a tagline; `draft_card_h` grows to fit. Play/live rows pass
`""` and are unchanged (they surface abilities via the zoom panel instead).

### 5. Draft screen (#5)

In `handle`, change `elif not self.detail.rect.collidepoint(event.pos):` to `else:` so any
tap except Select dismisses the zoom. Pass `card_tagline(ath)` to `athlete_card`.

### 6. Play + LivePlay screens -- tap-to-zoom (#7)

Add `zoom_idx` + a `PlayerDetail`. Tapping a player row opens the zoom (instead of
setting active immediately). While zoomed, the Select button sets `active_id` and closes;
any other tap closes. SIM auto-pick paths still set `active_id` directly (smokes unaffected).

### 7. Schedule -- team codes (#1)

`ScheduledGame` gains optional `home_abbr` / `away_abbr` (default `""`). New
`short_title()` returns `"NED v SWE"` using the abbr fields, falling back to
`_derive_abbr(name)` (uppercased first 3 letters of the longest word) when missing, and to
the round descriptor when teams are blank. `load_schedule` reads the optional fields.
`schedule.json` gets curated FIFA/MLS codes. Fixture picker uses `short_title()`.

### 8. Kickoff countdown after pick (#2)

`start_live(..., kickoff_utc="")` seeds the feed kickoff from the picked schedule game so
the existing lobby countdown (`LiveWaitScreen._draw_pregame`) fires for every game, not
only those in `live.fixtures`. `start_live_select.picked` looks up the picked game and
passes its `kickoff_utc`.

### 9. Back button on the lobby (#3)

`LiveWaitScreen(..., on_back=None)`: when provided, draw a top-left back button; a tap
fires `on_back` (checked before the SIM skip-tap). `start_live` passes `on_back=to_picker`
to the initial lobby only (not mid-draft / mid-play -- avoids co-op desync).

## Testing

- `tests/test_ability_text.py` (new): `role_summary`, `effect_lines` for explicit
  `DraftedAthlete` instances (ST/GK/AM), number formatting, `card_tagline`.
- `tests/test_schedule.py` (extend): `short_title` with abbr, with derivation, with blank
  teams; `_derive_abbr` cases.
- Run full `pytest tests/`, then the four SIM smokes, then build + package the deploy zip.

## Out of scope

Live-screen score-line team names (the complaint was the fixture list). Back buttons on
draft/live-play. Changing any scoring/power math (describer only reads existing effects).
