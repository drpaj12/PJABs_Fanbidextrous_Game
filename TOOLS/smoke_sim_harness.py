# TOOLS/smoke_sim_harness.py
"""Headless smoke for the REALTIME SIM HARNESS, accelerated (stepped) mode, solo.

Drives start_sim_realtime(rate=0.0, offset=+20, solo=True) under the SDL dummy driver with
no display and no network, pumping frames and injecting the SIM hotkeys the developer would
press: F steps the virtual clock to the next window boundary, S continues a resolved window.
SIM auto-advances splash / shop / recap, so only the play screens need input.

Asserts the live SEAM behaves as the live game would:
  1. Late join at +20 defaults the windows whose predict-deadline already passed (catch-up),
     so the FIRST window the player actually edits is NOT window 1.
  2. The crawl reaches the half recap (DungeonHalfScreen) and then the final (DungeonFinalScreen),
     i.e. extra-time absorbs and the half re-anchors to the second half.
  3. The DiagLog captured the expected trail: a KICKOFF line, at least one QUERY, a CATCH-UP
     target, a FORCE-RESOLVE, and a RE-ANCHOR (half 2).

Run:  .venv/Scripts/python TOOLS/smoke_sim_harness.py
ASCII-only output. Needs no display and no network."""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame  # noqa: E402
from src.ui.app import App  # noqa: E402
from src.ui import flow  # noqa: E402
from src.ui.screens.party_play_screen import PartyPlayScreen  # noqa: E402
from src.ui.screens.shop_screen import ShopScreen  # noqa: E402
from src.ui.screens.status_screens import DungeonHalfScreen  # noqa: E402
from src.utils.constants import CONFIG  # noqa: E402

_TEST_SIM = CONFIG["launcher"]["test_sim"]
_OFFSET = 20
_MAX_FRAMES = 4000
_F_COOLDOWN = 8                 # frames between F steps, so each async resolve settles first


class RecordingApp(App):
    """Real App (dummy SDL surface) that records set_screen targets (type names + objects)."""
    def __init__(self) -> None:
        super().__init__()
        self.screens: list = []
        self.play_screens: list = []

    def set_screen(self, screen) -> None:
        self.screens.append(type(screen).__name__)
        if isinstance(screen, PartyPlayScreen):
            self.play_screens.append(screen)
        super().set_screen(screen)


def _key(k: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="")


def _click(pos: tuple) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)


async def _pump(app: RecordingApp, frames: int) -> None:
    cooldown = 0
    for _ in range(frames):
        injected = []
        cur = app.current
        if isinstance(cur, ShopScreen):
            injected = [_key(pygame.K_r)]                # auto-buy + descend into window 1
            cooldown = 0
        elif isinstance(cur, DungeonHalfScreen):
            injected = [_key(pygame.K_s)]                # continue past the half recap
            cooldown = 0
        elif isinstance(cur, PartyPlayScreen):
            if cur.phase == "edit":
                injected = [_click(cur.action_btn.rect.center)]   # Submit the current dials
                cooldown = 0
            elif cur.phase == "resolved":
                injected = [_key(pygame.K_s)]            # continue the resolved window
                cooldown = 0
            elif not cur._polling and cooldown <= 0:     # wait phase
                injected = [_key(pygame.K_f)]            # step the virtual clock one boundary
                cooldown = _F_COOLDOWN
        cooldown -= 1
        for event in injected:
            if not (app.global_handler and app.global_handler(event)):
                if app.current is not None:
                    app.current.handle(event)
        if app.current is not None:
            app.current.update(1.0 / 60.0)
        app.screen.fill((0, 0, 0))
        if app.current is not None:
            app.current.draw(app.screen)
        await asyncio.sleep(0)
        if "DungeonFinalScreen" in app.screens:
            break


async def _run(app: RecordingApp) -> None:
    flow.start_sim_realtime(app, "drpaj", _TEST_SIM, rate=0.0,
                            offset_minutes=_OFFSET, solo=True)
    await _pump(app, _MAX_FRAMES)


def main() -> None:
    app = RecordingApp()
    asyncio.run(_run(app))
    seen = app.screens

    assert "SplashScreen" in seen, f"FAIL harness never started: {seen}"
    assert app.play_screens, f"FAIL no play window was ever shown: {seen}"

    first_window = app.play_screens[0].window
    assert first_window > 1, (
        f"FAIL late join at +{_OFFSET} did not default window 1 "
        f"(first edited window was {first_window})")

    assert "DungeonHalfScreen" in seen, f"FAIL never reached the half recap: {seen}"
    assert "DungeonFinalScreen" in seen, f"FAIL never reached the final: {seen}"

    diag = app.play_screens[0].diag
    lines = diag.all_lines() if diag is not None else []
    blob = "\n".join(lines)
    for kind in ("KICKOFF", "QUERY", "CATCH-UP", "FORCE-RESOLVE", "RE-ANCHOR"):
        assert kind in blob, f"FAIL diag trail missing {kind}\n--- diag ---\n{blob}"

    print(f"OK first edited window = {first_window} (window 1 defaulted by catch-up)")
    print(f"OK reached half recap and final; "
          f"screens={[s for i, s in enumerate(seen) if s not in seen[:i]]}")
    print(f"OK diag trail has KICKOFF/QUERY/CATCH-UP/FORCE-RESOLVE/RE-ANCHOR "
          f"({len(lines)} lines)")
    print("OK smoke complete")


if __name__ == "__main__":
    main()
