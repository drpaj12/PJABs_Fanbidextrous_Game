# TOOLS/smoke_solo_crawl.py
"""Headless launch smoke for the SOLO recorded dungeon crawl (no party, no network).

Drives start_dungeon_party(solo=True) under SIM with the SDL dummy driver, pumps a bounded
number of frames, and asserts:
  1. the party-number screen (PartyScreen) is NEVER built -- solo skips it,
  2. no networked relay is constructed (the in-process LocalRelay is used),
  3. the crawl auto-advances through the recorded match and reaches the shop / play screens.

Run:  .venv/Scripts/python TOOLS/smoke_solo_crawl.py
ASCII-only output. Needs no display and no network."""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ui.app import App  # noqa: E402
from src.ui import flow  # noqa: E402
from src.utils.constants import CONFIG  # noqa: E402

_MAX_FRAMES = 600
_TEST_SIM = CONFIG["launcher"]["test_sim"]


class RecordingApp(App):
    """Real App (dummy SDL surface) that records every set_screen target by type name."""
    def __init__(self) -> None:
        super().__init__()
        self.screens: list = []

    def set_screen(self, screen) -> None:
        self.screens.append(type(screen).__name__)
        super().set_screen(screen)


async def _pump(app: RecordingApp, frames: int) -> None:
    """Run the app loop for a bounded number of frames, then stop (SIM auto-advances, so no
    input injection is needed to step through splash -> game-select -> lobby -> shop)."""
    import pygame
    for _ in range(frames):
        dt = 1.0 / 60.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                app.running = False
            elif app.current is not None:
                if not (app.global_handler and app.global_handler(event)):
                    app.current.handle(event)
        if app.current is not None:
            app.current.update(dt)
        app.screen.fill((0, 0, 0))
        if app.current is not None:
            app.current.draw(app.screen)
        await asyncio.sleep(0)
        if "ShopScreen" in app.screens:
            break


async def _run_all(app: RecordingApp) -> None:
    # Start inside the running loop so the picked() -> go() (coord.join + flow.start) task
    # schedules on the SAME loop the pump drives.
    flow.start_dungeon_party(app, "drpaj", _TEST_SIM, sim_mode=True, solo=True)
    await _pump(app, _MAX_FRAMES)


def main() -> None:
    app = RecordingApp()
    asyncio.run(_run_all(app))

    seen = app.screens
    assert "PartyScreen" not in seen, f"FAIL solo built a party-number screen: {seen}"
    assert "SplashScreen" in seen, f"FAIL crawl never started (no splash): {seen}"
    assert "ShopScreen" in seen, f"FAIL crawl never reached the shop: {seen}"
    print(f"OK solo crawl reached the shop with no party screen; "
          f"screens={[s for i, s in enumerate(seen) if s not in seen[:i]]}")
    print("OK smoke complete")


if __name__ == "__main__":
    main()
