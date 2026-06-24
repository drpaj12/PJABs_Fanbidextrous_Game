# Live Dungeon-Crawl Flow (picking + windows)

This is the canonical description of how picking and resolution work in the LIVE dungeon
crawl. (The user asked for this written down as "main.md" -- it lives here so it sits with the
other design docs.) ASCII-only.

---

## Status: SOLO first (co-op disabled for now)

As of 2026-06-23 the live crawl ships **solo**. The co-op/party layer (shared PHP relay,
leader/follower reconcile, waiting on other players) is disabled because it could hang
(a leader who submitted picks then waited forever). The dungeon mechanics themselves are
unchanged -- they just run as a **party of one that is always the leader** over an in-process
`LocalRelay` (no network coordination). Re-enabling co-op is a one-line swap of `LocalRelay`
back to `RelayClient` (see `start_dungeon_party_live(..., solo=...)` in `src/ui/flow.py`).

Two deployed modes:
- **Live dungeon crawl** -- real match feed (`start_dungeon_party_live(solo=True)`).
- **Test crawl (recorded match)** -- a bundled recording, SIM hotkeys to step fast
  (`start_dungeon_party(solo=True)`).

The live MATCH feed (lineups, score, clock) is a separate channel from the (now in-process)
party relay and is polled exactly as before; only the lead client spends API quota.

---

## Windows

A match is diced into **15-minute windows**, 3 per half (config: `window_seconds=900`,
`half_minutes=45`, `windows_per_half=3`):

- First half:  W1 = 0-15', W2 = 15-30', W3 = 30-45' (+ first-half stoppage / extra time).
- Second half: W4 = 45-60', W5 = 60-75', W6 = 75-90' (+ second-half stoppage / extra time).

Each window engages monsters; the player's per-window prediction lines (goals / shots /
corners / cards / fouls) drive how far the party advances and how much gold it earns. The
extra-time window of each half has no fixed end minute -- it resolves once the feed reports
the half is over (`halftime`/`finished` status).

---

## Intended picking model (target design)

The target model is **predict one window ahead**: the prediction for window W is locked
*before* W starts, and W resolves at W's end (once the live feed actually covers the window's
end minute -- not at the bare clock boundary, so the actuals query lands inside the window
instead of grading against stale cumulative totals).

Timeline a player experiences:

1. **Pre-game (~5-15 min before kickoff):** pick the loadout (shop), then make the W1
   prediction.
2. **During W1 (0-15' playing):** make the W2 prediction. A latecomer joining here is
   auto-assigned default W1 picks.
3. **During W2 (15-30'):** W1 resolves; make the W3 prediction. A latecomer here is caught up
   with defaults + resolution for the windows already played.
4. **During W3 (30-45'+ET):** no new predictions -- just watch the half finish. The first-half
   dungeon (W1-W3) resolves out by halftime.
5. **Halftime:** receive the accumulated gold; buy items for the second-half dungeon (unused
   items carry over). Complete the W4 prediction before W4 starts. Clients guess when to poll
   to detect the match resuming; the lead client polls about every 2 minutes to bound API use.
6. **During W4 (45-60'):** W4 resolves; make the W5 prediction; a latecomer gets default W4.
7. **During W5 (60-75'):** make the W6 prediction.
8. **During W6 (75-90'+ET):** just watch; the final resolution comes in.

### Catch-up (latecomer / mid-match join)

On entering a live match already in progress, every window the feed has *fully covered*
auto-resolves using the player's locked pick (or default lines), applying their loadout, so the
player lands on the CURRENT live window and is gated there until real data arrives. If catch-up
crosses halftime, the second-half per-player treasury is granted automatically (no manual
mid-catch-up shop) and the loadout carries over.

Pure helpers: `windows_elapsed()` (count of fully-covered windows) and `window_data_ready()`
(is this window's data in the feed yet) in `src/game/live_catchup.py` + `src/game/half_clock.py`.

---

## What the code does TODAY (and the gap)

The shipped live path currently uses a **predict-current-window** timing (the player edits the
first unresolved window; the pick locks when that window starts playing via the match clock's
`editing_window`, and resolves when the feed covers that window's end). This differs from the
"one window ahead" target above. Closing that gap (shifting the edit target one window ahead,
plus the halftime-batched first-dungeon resolution) is the next design step once the solo base
loop is confirmed working. Until then, the solo path proves the mechanics: shop -> per-window
picks -> resolve -> gold -> halftime shop -> second half -> final percentage.

---

## SIM / testing

`Test crawl (recorded match)` (`--party` on desktop, or the launcher button) runs the whole
crawl deterministically over a recording with SIM hotkeys so it can be stepped through fast
without waiting on a live game:

- `H` show / hide the hotkey help
- `R` auto-draft / auto-buy then go
- `A` auto-pick predictions
- `S` skip / continue
- `F` fast-forward the current window (auto-pick straight to resolution)

Desktop entry points: `--party` (recorded, solo) and `--sololive [--simlive]` (real feed, solo).
