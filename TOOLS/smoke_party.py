# TOOLS/smoke_party.py
"""Headless party smoke: in-memory relay, 3 coordinators (leader + 2 followers), a full
2-half crawl with the per-player economy, then draw the three party screens. ASCII-only.
Run from repo root:  .venv/Scripts/python TOOLS/smoke_party.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from tests.test_party_coordinator import FakeRelay, _pool, _actuals
from src.sync.party_coordinator import PartyCoordinator
from src.utils.constants import CONFIG

_WPH = int(CONFIG["game"]["windows_per_half"])
_PER = int(CONFIG["party"]["per_player_treasury"])


async def _drive() -> int:
    relay, pool = FakeRelay(), _pool()
    lead = PartyCoordinator(relay, 0, "drpaj", pool, _actuals)
    a = PartyCoordinator(relay, 0, "alice", pool, _actuals)
    b = PartyCoordinator(relay, 0, "bob", pool, _actuals)
    members = (lead, a, b)
    for c in members:
        await c.join()
    assert lead.is_leader and not a.is_leader, "leader assignment FAIL"

    for half in (1, 2):
        if half == 1:
            await lead.leader_start()
        for c in members:
            await c.refresh()
            await c.submit_loadout([], c.shop_budget())
        await lead.leader_try_reconcile_shop()
        for c in members:
            await c.refresh()
        assert lead.phase() == "play", f"half {half} not in play: {lead.phase()}"
        for w in range(1, _WPH + 1):
            for c in members:
                await c.submit_pick(w, {"goal": 1, "shot": 3, "corner": 3,
                                        "card": 1, "foul": 4})
            await lead.refresh()
            await lead.leader_try_resolve(w)
            for c in members:
                await c.refresh()
            assert lead.resolved_through() == w, f"window {w} not resolved"
            assert a.view()["depth"] == lead.view()["depth"], "follower depth mismatch FAIL"
        await lead.leader_advance_half()
        for c in members:
            await c.refresh()

    assert lead.phase() == "done", f"did not finish: {lead.phase()}"
    pct = lead.view()["percent"]
    print(f"OK  crawl complete  depth={lead.view()['depth']}  percent={pct}%  "
          f"gold drpaj={lead.my_treasury()} alice={a.my_treasury()} bob={b.my_treasury()}")
    return pct


def _draw_screens() -> None:
    import pygame
    pygame.init()
    pygame.display.set_mode((CONFIG["display"]["width"], CONFIG["display"]["height"]))
    from src.ui.app import App
    from src.ui.screens.party_screen import PartyScreen
    from src.ui.screens.party_lobby_screen import PartyLobbyScreen
    from src.ui.screens.party_play_screen import PartyPlayScreen
    relay, pool = FakeRelay(), _pool()
    coord = PartyCoordinator(relay, 0, "drpaj", pool, _actuals)
    asyncio.run(coord.join())
    app = App()
    PartyScreen(app, "drpaj", lambda n: None, None).draw(app.screen)
    PartyLobbyScreen(app, coord, lambda: None, lambda: None, "Start", None).draw(app.screen)
    PartyPlayScreen(app, coord, 1, "H1 W1", lambda: None, True, None, None).draw(app.screen)
    print("OK  drew party / lobby / play screens")


def main() -> None:
    pct = asyncio.run(_drive())
    _draw_screens()
    if pct <= 0:
        print("FAIL  crawl made no progress")
        sys.exit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
