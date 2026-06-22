# TOOLS/smoke_dungeon.py
"""Headless integration smoke for the SIM dungeon: run a full two-half crawl on the test
sim via CrawlSession + feed actuals, then construct and draw every new screen once.

Run:  .venv/Scripts/python TOOLS/smoke_dungeon.py
ASCII-only output. Uses the SDL dummy driver so it needs no display."""
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame  # noqa: E402

from src.ui.app import App  # noqa: E402
from src.game.crawl import CrawlSession  # noqa: E402
from src.game.replay_feed import ReplayFeed  # noqa: E402
from src.game.normalize_soccer import actuals_from_raw  # noqa: E402
from src.game.score import total_tiles_game  # noqa: E402
from src.ui.flow import _pool_from_feed  # noqa: E402
from src.ui.sim import SimMode  # noqa: E402
from src.ui.screens.shop_screen import ShopScreen  # noqa: E402
from src.ui.screens.dungeon_play_screen import DungeonPlayScreen  # noqa: E402
from src.ui.screens.status_screens import DungeonFinalScreen  # noqa: E402
from src.utils.constants import CONFIG, load_data  # noqa: E402

_SIM = CONFIG["launcher"]["test_sim"]
_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_HALF_MIN = CONFIG["game"]["half_minutes"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_WINDOWS = CONFIG["game"]["windows_per_half"]


def _actuals(feed, half, window):
    start = (half - 1) * _HALF_MIN + (window - 1) * _WINDOW_MIN
    a = feed.snapshot_at(start)
    b = feed.snapshot_at(start + _WINDOW_MIN)
    raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
    return actuals_from_raw(raw, _STATS_MENU)


def main() -> None:
    feed = ReplayFeed.from_file(_SIM)
    pool = _pool_from_feed(feed)
    assert pool, "FAIL sim feed has no lineup"
    session = CrawlSession(party_size=1, pool=pool, rng=random.Random(99))
    print(f"OK loaded sim: {len(pool)} athletes, treasury {session.treasury}")

    for category in ("weapon", "armor"):
        for item in session.catalog():
            if item.category == category and session.buy(0, item)[0]:
                print(f"OK bought {category}: {item.name} ({item.price}g)")
                break

    lines = {"goal": 1, "shot": 2, "corner": 3, "card": 1, "foul": 4}
    for half in (1, 2):
        for window in range(1, _WINDOWS + 1):
            if session.half_over():
                break
            res = session.resolve_window([lines], _actuals(feed, half, window),
                                         f"H{half} W{window}")
            print(f"OK H{half} W{window}: +{res.tiles_advanced} tiles ({res.color}), "
                  f"depth {session.state.depth}, gold {session.treasury}")
        if half == 1:
            session.begin_second_half()
            print("OK begin second half")

    total = total_tiles_game(session.party_size)
    print(f"OK final score: {session.score_label()}")
    assert 0 <= session.percent() <= 100, "FAIL percent out of range"

    app = App()
    fresh = CrawlSession(party_size=1, pool=pool, rng=random.Random(99))
    ShopScreen(app, fresh, lambda: None, SimMode(True)).draw(app.screen)
    print("OK ShopScreen draws")
    play = DungeonPlayScreen(app, fresh, feed, 1, "First Half -- Window 1/3",
                             lambda ln: fresh.resolve_window([ln], _actuals(feed, 1, 1), "H1 W1"),
                             lambda: None, SimMode(True))
    play.draw(app.screen)
    play._descend()
    play.draw(app.screen)
    print("OK DungeonPlayScreen draws (both phases)")
    DungeonFinalScreen(app, session.percent(), session.cleared_total(), total).draw(app.screen)
    print("OK DungeonFinalScreen draws")
    print("OK smoke complete")


if __name__ == "__main__":
    main()
