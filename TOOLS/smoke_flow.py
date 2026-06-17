# TOOLS/smoke_flow.py
"""Headless smoke test: drive the full SIM flow to FinalScreen, no window.

Run: SDL_VIDEODRIVER=dummy .venv/Scripts/python TOOLS/smoke_flow.py [slug]
Steps the app loop manually (App.run is an endless coroutine) feeding SIM hotkeys
appropriate to whichever screen is current, and asserts we reach FinalScreen with
no exception inside a bounded number of frames.
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from src.ui.app import App
from src.ui import flow
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
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
            print("OK reached FinalScreen at frame", frame)
            print("OK screens seen:", sorted(seen))
            print("OK play windows entered:", windows_played)
            return 0

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


if __name__ == "__main__":
    raise SystemExit(main())
