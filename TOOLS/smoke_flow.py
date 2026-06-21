# TOOLS/smoke_flow.py
"""Headless smoke tests: drive the game with no real window, no network.

Two independent checks run from __main__ (both must pass for exit 0):

1. Offline SIM flow -- Splash -> ... -> FinalScreen via SIM hotkeys (see main()).
2. Live-screen lifecycle -- drive LivePlayScreen directly with an injected wall clock
   and a pre-warmed LiveFeed (no asyncio loop, no relay): assert each window locks in
   order and on_finished fires at half time (see live_smoke()).

Run: SDL_VIDEODRIVER=dummy .venv/Scripts/python TOOLS/smoke_flow.py [slug]
The first arg, if given, selects the offline simulation slug only.
"""
import os
import sys

# Allow running directly (python TOOLS/smoke_flow.py) -- put the repo root, not
# TOOLS/, on sys.path so `import src...` resolves the same way pytest does.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from src.ui.app import App
from src.ui import flow
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
from src.ui.screens.pregame_screen import PregameScreen
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.ui.screens.cinematic_screen import CinematicScreen
from src.ui.screens.status_screens import FinalScreen


def _key(k: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="")


def _click() -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(207, 448))


def _drive(screen, sim) -> list[pygame.event.Event]:
    """Pick the SIM input(s) to push the current screen forward."""
    if sim.show_help:
        return [_click()]  # dismiss the help popup first
    if isinstance(screen, SplashScreen):
        return [_key(pygame.K_s)]
    if isinstance(screen, RoomScreen):
        return []  # auto-creates on update once popup is gone
    if isinstance(screen, PregameScreen):
        return []  # auto-advances on update in SIM
    if isinstance(screen, DraftScreen):
        return [_key(pygame.K_r)]  # auto-draft 6 + lock
    if isinstance(screen, PlayScreen):
        return [_key(pygame.K_f)]  # fast-forward: auto-pick + submit
    if isinstance(screen, CinematicScreen):
        return [_key(pygame.K_s)]  # skip animation
    return []


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else None
    app = App()
    if slug:
        flow.start_simulation(app, f"assets/data/simulations/{slug}.json", sim_mode=True)
    else:
        flow.start(app, sim_mode=True)

    sim = app.global_handler.__self__  # SimMode (handle_global is its bound method)

    seen = set()
    windows_played = 0
    prev = None
    MAX_FRAMES = 6000
    for frame in range(MAX_FRAMES):
        cur = app.current
        seen.add(type(cur).__name__)
        if isinstance(cur, PlayScreen) and cur is not prev:
            windows_played += 1
        prev = cur
        if isinstance(cur, FinalScreen):
            ok = windows_played == 10  # 9 regular + 1 extra time
            print(("OK" if ok else "FAIL"), "reached FinalScreen at frame", frame)
            print("OK screens seen:", sorted(seen))
            print(("OK" if ok else "FAIL"), "play windows entered:", windows_played,
                  "(expected 10)")
            return 0 if ok else 1

        for ev in _drive(cur, sim):
            if not (app.global_handler and app.global_handler(ev)):
                cur.handle(ev)
        cur.update(0.5)  # big dt to blow past timed animations fast
        app.screen.fill((0, 0, 0))
        cur.draw(app.screen)
        if app.overlay is not None:
            app.overlay(app.screen)

    print("FAIL never reached FinalScreen in", MAX_FRAMES, "frames")
    print("FAIL screens seen:", sorted(seen), "windows:", windows_played)
    return 1


# --------------------------------------------------------------------------- #
# Live-screen lifecycle smoke
# --------------------------------------------------------------------------- #
# Drives LivePlayScreen with NO pygame event loop and NO network. The LiveFeed is
# pre-warmed with relay-shaped snapshots built from flow._demo_script, and time is fed
# through an injected now_fn the driver advances 60s per step. The screen's poll path is
# fire-and-forget (asyncio.ensure_future); with the feed already warm it never blocks, so
# update() drives the window boundary logic deterministically off the injected clock.

# Reverse of normalize_soccer._STAT_FIELD: engine field -> API-Football statistic "type".
# goals are carried on the fixture payload (not the statistics endpoint), so they are not
# emitted here as a statistic row.
_FIELD_TO_API = {
    "corner_kicks": "Corner Kicks",
    "shots_on_goal": "Shots on Goal",
    "fouls": "Fouls",
    "cards": "Yellow Cards",
}


def _relay_snapshot(stats: dict, elapsed: int, status_short: str) -> dict:
    """Build one relay-shaped snapshot (the feed_cache.php shape LiveFeed.record ingests)
    from a flat demo stats dict at a given match minute/status."""
    rows = [{"type": _FIELD_TO_API[f], "value": stats.get(f, 0)}
            for f in _FIELD_TO_API]
    return {
        "fixture": {"response": [{
            "fixture": {"status": {"short": status_short, "elapsed": elapsed},
                        "date": "2026-06-20T00:00:00+00:00"},
            "teams": {"home": {"name": "Canada"}, "away": {"name": "Mexico"}},
            "goals": {"home": stats.get("goals", 0), "away": 0},
        }]},
        "statistics": {"response": [{"statistics": rows}]},
        "lineups": {"response": []},
    }


def live_smoke() -> int:
    """Drive LivePlayScreen through a full first half headlessly. Returns 0 on OK."""
    from src.ui.app import App
    from src.ui import flow
    from src.game.live_feed import LiveFeed
    from src.game.half_clock import HalfClock
    from src.game.match_clock import MatchClock
    from src.game.window_report import build_window_report
    from src.ui.sim import SimMode
    from src.ui.screens.live_play_screen import LivePlayScreen
    from src.sync.feed_client import FeedClient
    from src.utils.constants import CONFIG

    half_min = CONFIG["game"]["half_minutes"]
    window_min = CONFIG["game"]["window_seconds"] // 60
    poll_seconds = CONFIG["feed"]["poll_seconds"]
    stat_labels = flow._STAT_LABELS

    # Pre-warm the feed with the in-play (1H) snapshots only. The final halftime snapshot
    # is withheld and recorded by the driver once the injected clock reaches it -- otherwise
    # the feed would report halftime on the first update() and short-circuit the boundary
    # logic before any window locks. The demo script reports halftime at minute 48 (3
    # minutes of first-half stoppage).
    demo = flow._demo_script()
    halftime_snap = demo["snapshots"][-1]
    halftime_minute = halftime_snap["minute"]
    feed = LiveFeed()
    for snap in demo["snapshots"][:-1]:                   # all but the halftime snapshot
        minute = snap["minute"]
        feed.record(_relay_snapshot(snap["stats"], minute, "1H"), minute=minute)

    clock = HalfClock(half_min, window_min)
    et_window = clock.extra_time_window

    # Manually-advanced wall clock. kickoff at epoch 0; advance 60s per loop -> 1 match
    # minute per step, so window boundaries (every window_min minutes) pass on schedule.
    holder = {"t": 0.0}
    now_fn = lambda: holder["t"]
    match_clock = MatchClock(kickoff_epoch=0.0, clock=clock)
    editing_start = match_clock.editing_window(now_fn())

    available = flow._demo_pool()[:6]

    locks: list[int] = []

    def on_lock(window, preds, active_id, use_power):
        """Record the lock and return a valid WindowReport (scoring is unit-tested
        elsewhere; this only feeds the screen's inline-reveal path)."""
        locks.append(window)
        return build_window_report(
            window=window, predictions=preds, actuals={},
            stat_labels=stat_labels, success_value=0, concede_value=0,
            success_threshold=CONFIG["meter"]["success_threshold"],
            concede_threshold=CONFIG["meter"]["concede_threshold"],
            success_fired=False, concede_fired=False)

    finished = {"done": False}

    def on_finished():
        finished["done"] = True

    app = App()
    feed_client = FeedClient(CONFIG["relay"]["base_url"],
                             feed_path=CONFIG["relay"]["feed_path"], is_lead=True)
    sim = SimMode(False)
    screen = LivePlayScreen(
        app=app, feed=feed, feed_client=feed_client, match_clock=match_clock,
        fixture_id=1, editing_window_start=editing_start, on_lock=on_lock,
        on_finished=on_finished, poll_seconds=poll_seconds, available=available,
        now_fn=now_fn, sim=sim)

    ok = True
    for step in range(0, 55):
        holder["t"] += 60.0                  # advance one match minute
        minute = int(holder["t"] // 60)
        if minute >= halftime_minute:        # half-time snapshot arrives on the clock
            feed.record(_relay_snapshot(halftime_snap["stats"], minute, "HT"),
                        minute=minute)
        screen._auto_pick()                  # lock all dials + pick an active player
        screen.update(0.0)
        if finished["done"]:
            break

    expected = list(range(editing_start, et_window + 1))
    in_order = locks == sorted(locks)
    locked_expected = locks == expected
    if not (finished["done"] and in_order and locked_expected):
        ok = False

    print(("OK" if locked_expected else "FAIL"),
          "live smoke: locked windows =", locks, "(expected", expected, ")")
    print(("OK" if in_order else "FAIL"), "live smoke: windows locked in order")
    print(("OK" if finished["done"] else "FAIL"),
          "live smoke: reached final screen (on_finished fired)")
    return 0 if ok else 1


def _demo_script_2h() -> dict:
    """A full second half: cumulative stats every 5 minutes at ABSOLUTE match minutes
    45-90 (feed snapshots are keyed by absolute minute), plus 3 minutes of stoppage
    (90 -> 93) with a full-time status at minute 93."""
    return {
        "snapshots": [
            {"minute": 45, "stats": {"corner_kicks": 9,  "shots_on_goal": 9,  "fouls": 17, "goals": 2, "cards": 2}},
            {"minute": 50, "stats": {"corner_kicks": 10, "shots_on_goal": 10, "fouls": 19, "goals": 2, "cards": 2}},
            {"minute": 55, "stats": {"corner_kicks": 11, "shots_on_goal": 11, "fouls": 21, "goals": 2, "cards": 3}},
            {"minute": 60, "stats": {"corner_kicks": 12, "shots_on_goal": 12, "fouls": 23, "goals": 2, "cards": 3}},
            {"minute": 65, "stats": {"corner_kicks": 13, "shots_on_goal": 13, "fouls": 25, "goals": 3, "cards": 3}},
            {"minute": 70, "stats": {"corner_kicks": 14, "shots_on_goal": 14, "fouls": 27, "goals": 3, "cards": 3}},
            {"minute": 75, "stats": {"corner_kicks": 15, "shots_on_goal": 15, "fouls": 29, "goals": 3, "cards": 4}},
            {"minute": 80, "stats": {"corner_kicks": 16, "shots_on_goal": 16, "fouls": 31, "goals": 3, "cards": 4}},
            {"minute": 85, "stats": {"corner_kicks": 17, "shots_on_goal": 17, "fouls": 33, "goals": 4, "cards": 4}},
            {"minute": 90, "stats": {"corner_kicks": 18, "shots_on_goal": 18, "fouls": 35, "goals": 4, "cards": 4}},
            {"minute": 93, "stats": {"corner_kicks": 19, "shots_on_goal": 18, "fouls": 37, "goals": 4, "cards": 4}},
        ],
    }


def live_smoke_2h() -> int:
    """Drive LivePlayScreen through a full SECOND half headlessly. Mirrors live_smoke()
    but with a start_minute=45 clock: feed snapshots are keyed by absolute match minute
    (45-93), the in-play status is 2H (-> live) and the terminal status is FT (-> finished).
    Asserts the 2H windows lock in order, the per-poll re-align does not break ordering, and
    on_finished fires at full time. Returns 0 on OK."""
    from src.ui.app import App
    from src.ui import flow
    from src.game.live_feed import LiveFeed
    from src.game.half_clock import HalfClock
    from src.game.match_clock import MatchClock
    from src.game.window_report import build_window_report
    from src.ui.sim import SimMode
    from src.ui.screens.live_play_screen import LivePlayScreen
    from src.sync.feed_client import FeedClient
    from src.utils.constants import CONFIG

    half_min = CONFIG["game"]["half_minutes"]
    window_min = CONFIG["game"]["window_seconds"] // 60
    poll_seconds = CONFIG["feed"]["poll_seconds"]
    resync_threshold = CONFIG["live"]["resync_threshold_seconds"]
    second_half_label = CONFIG["game"]["second_half_label"]
    stat_labels = flow._STAT_LABELS

    # Pre-warm with the in-play (2H) snapshots only; withhold the full-time snapshot so the
    # feed does not report finished on the first update() and short-circuit before any window
    # locks. The driver records FT once the injected clock reaches it.
    demo = _demo_script_2h()
    ft_snap = demo["snapshots"][-1]
    ft_minute = ft_snap["minute"]                        # absolute (93)
    feed = LiveFeed()
    for snap in demo["snapshots"][:-1]:                   # all but the full-time snapshot
        minute = snap["minute"]
        feed.record(_relay_snapshot(snap["stats"], minute, "2H"), minute=minute)

    clock = HalfClock(half_min, window_min, start_minute=half_min)   # second-half clock
    et_window = clock.extra_time_window

    # Wall clock anchored at the second-half kickoff (epoch 0 == in-half minute 0); advance
    # 60s per loop so one in-half match minute passes per step.
    holder = {"t": 0.0}
    now_fn = lambda: holder["t"]
    match_clock = MatchClock(kickoff_epoch=0.0, clock=clock)
    editing_start = match_clock.editing_window(now_fn())

    available = flow._demo_pool()[:6]

    locks: list[int] = []

    def on_lock(window, preds, active_id, use_power):
        locks.append(window)
        return build_window_report(
            window=window, predictions=preds, actuals={},
            stat_labels=stat_labels, success_value=0, concede_value=0,
            success_threshold=CONFIG["meter"]["success_threshold"],
            concede_threshold=CONFIG["meter"]["concede_threshold"],
            success_fired=False, concede_fired=False)

    finished = {"done": False}

    def on_finished():
        finished["done"] = True

    app = App()
    feed_client = FeedClient(CONFIG["relay"]["base_url"],
                             feed_path=CONFIG["relay"]["feed_path"], is_lead=True)
    sim = SimMode(False)
    screen = LivePlayScreen(
        app=app, feed=feed, feed_client=feed_client, match_clock=match_clock,
        fixture_id=1, editing_window_start=editing_start, on_lock=on_lock,
        on_finished=on_finished, poll_seconds=poll_seconds, available=available,
        half_label=second_half_label, resync_threshold_seconds=resync_threshold,
        now_fn=now_fn, sim=sim)

    ok = True
    for step in range(0, 55):
        holder["t"] += 60.0                  # advance one in-half match minute
        abs_minute = half_min + int(holder["t"] // 60)   # absolute match minute
        if abs_minute >= ft_minute:          # full-time snapshot arrives on the clock
            feed.record(_relay_snapshot(ft_snap["stats"], abs_minute, "FT"),
                        minute=abs_minute)
        screen._auto_pick()                  # lock all dials + pick an active player
        screen.update(0.0)
        if finished["done"]:
            break

    expected = list(range(editing_start, et_window + 1))
    in_order = locks == sorted(locks)
    locked_expected = locks == expected
    if not (finished["done"] and in_order and locked_expected):
        ok = False

    print(("OK" if locked_expected else "FAIL"),
          "live 2H smoke: locked windows =", locks, "(expected", expected, ")")
    print(("OK" if in_order else "FAIL"), "live 2H smoke: windows locked in order")
    print(("OK" if finished["done"] else "FAIL"),
          "live 2H smoke: reached final screen (on_finished fired)")
    return 0 if ok else 1


def schedule_smoke() -> int:
    """Drive the dynamic FixtureSelectScreen headlessly with a synthetic schedule + a fixed
    now_fn. Asserts the visible set is the rolling-window subset sorted soonest-first, that a
    finished game is not playable, and that SIM auto-picks the first PLAYABLE visible game's
    id. Returns 0 on OK."""
    from datetime import datetime, timezone, timedelta
    from src.ui.app import App
    from src.game.schedule import ScheduledGame, visible_games
    from src.ui.screens.fixture_select_screen import FixtureSelectScreen
    from src.ui.sim import SimMode

    cfg = {"lookahead_hours": 48, "drop_after_hours": 4,
           "live_window_minutes": 150, "soon_minutes": 15}
    now = 1_000_000.0          # arbitrary fixed wall clock (epoch seconds)
    hour = 3600

    def g(gid: int, offset_h: float, home: str = "A", away: str = "B") -> ScheduledGame:
        ref = (datetime(1970, 1, 1, tzinfo=timezone.utc)
               + timedelta(seconds=now + offset_h * hour))
        return ScheduledGame(id=gid, competition="WC", home=home, away=away,
                             round="Group A", kickoff_utc=ref.isoformat(),
                             kickoff_local="TBD")

    games = [
        g(101, 2.0, "Soon", "One"),     # upcoming, in 2h  -> playable
        g(102, -1.0, "Live", "Now"),    # kicked off 1h ago -> live, playable
        g(103, -100.0, "Old", "Done"),  # long past         -> dropped by window
        g(104, 100.0, "Far", "Future"), # beyond lookahead  -> dropped by window
    ]

    # Expected visible set (sorted soonest-first): Live (-1h) then Soon (+2h).
    expect_titles = ["Live v Now", "Soon v One"]
    vis = visible_games(games, now, cfg)
    vis_ok = [x.title() for x in vis] == expect_titles

    app = App()
    picked: list[int] = []
    sim = SimMode(True)
    screen = FixtureSelectScreen(app, games, picked.append, cfg, sim, now_fn=lambda: now)
    screen.update(0.0)                  # SIM auto-pick on first update

    # First playable visible game is the live one (id 102).
    pick_ok = picked == [102]

    # Sanity: a draw pass must not raise (renders cards + chips for the visible set).
    draw_ok = True
    try:
        app.screen.fill((0, 0, 0))
        screen.draw(app.screen)
    except Exception as exc:            # pragma: no cover - smoke guard
        draw_ok = False
        print("FAIL schedule smoke: draw raised", exc)

    ok = vis_ok and pick_ok and draw_ok
    print(("OK" if vis_ok else "FAIL"),
          "schedule smoke: visible =", [x.title() for x in vis],
          "(expected", expect_titles, ")")
    print(("OK" if pick_ok else "FAIL"),
          "schedule smoke: SIM auto-picked =", picked, "(expected [102])")
    print(("OK" if draw_ok else "FAIL"), "schedule smoke: draw pass clean")
    return 0 if ok else 1


def resolve_smoke() -> int:
    """Drive LiveResolveScreen headlessly: a fake transport returns a live=all payload, and
    the screen must fire on_resolved with the REAL id whose teams match the picked game. Also
    asserts a non-matching pick keeps polling (never resolves). Returns 0 on OK."""
    import asyncio
    import json
    from src.ui.app import App
    from src.ui.sim import SimMode
    from src.sync.feed_client import FeedClient
    from src.ui.screens.live_resolve_screen import LiveResolveScreen

    payload = json.dumps({"response": [
        {"id": 1489397, "home": "Spain", "away": "Saudi Arabia", "status": "1H"},
        {"id": 1539006, "home": "Belgium", "away": "IR Iran", "status": "1H"},
    ], "cached_at": 0})

    class FakeTransport:
        async def get(self, url: str) -> str:
            return payload

    async def drive(home: str, away: str) -> list[int]:
        # Runs inside our dedicated loop, so the screen's fire-and-forget
        # ensure_future(self._poll()) schedules on it; awaiting sleep(0) lets it complete.
        app = App()
        client = FeedClient("http://x", transport=FakeTransport(), is_lead=True)
        got: list[int] = []
        screen = LiveResolveScreen(
            app, client, home, away, kickoff_iso="", on_resolved=got.append,
            poll_seconds=0.0, fallback_id=999, sim=SimMode(False))
        for _ in range(5):                  # update polls (ensure_future) + resolve attempt
            screen.update(0.1)
            await asyncio.sleep(0)          # let the poll task complete
            app.screen.fill((0, 0, 0))
            screen.draw(app.screen)         # draw must not raise
        return got

    # Use a dedicated loop WITHOUT set_event_loop so we never disturb the default loop the
    # live smokes left fire-and-forget poll tasks on (avoids spurious shutdown warnings).
    loop = asyncio.new_event_loop()
    try:
        match = loop.run_until_complete(drive("Belgium", "Iran"))   # IR Iran == Iran, swapped
        no_match = loop.run_until_complete(drive("Brazil", "Argentina"))
    finally:
        loop.close()

    match_ok = match == [1539006]
    nomatch_ok = no_match == []
    print(("OK" if match_ok else "FAIL"),
          "resolve smoke: matched id =", match, "(expected [1539006])")
    print(("OK" if nomatch_ok else "FAIL"),
          "resolve smoke: unmatched pick stays unresolved =", no_match, "(expected [])")
    return 0 if (match_ok and nomatch_ok) else 1


if __name__ == "__main__":
    rc_offline = main()
    rc_live = live_smoke()
    rc_live_2h = live_smoke_2h()
    rc_schedule = schedule_smoke()
    rc_resolve = resolve_smoke()
    raise SystemExit(rc_offline or rc_live or rc_live_2h or rc_schedule or rc_resolve)
