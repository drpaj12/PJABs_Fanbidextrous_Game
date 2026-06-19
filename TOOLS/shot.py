# TOOLS/shot.py
"""Headless screenshot harness: render specific screens to PNG so we can SEE what
the player sees (scroll arrows, layout) without a live window. Debug-only tool."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from src.ui.app import App
from src.ui import flow
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.utils.constants import CONFIG


def _render(app: App, screen) -> pygame.Surface:
    app.set_screen(screen)
    app.screen.fill(CONFIG["colors"]["background"])
    screen.draw(app.screen)
    return app.screen


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "TOOLS" / "_shots"
    out.mkdir(exist_ok=True)
    app = App()
    pool = flow._demo_pool()

    draft = DraftScreen(app, pool, lambda *_: None, None)
    print("DRAFT  max_scroll:", draft._max_scroll(),
          "viewport_h:", draft._viewport().height)
    pygame.image.save(_render(app, draft), str(out / "draft.png"))

    play = PlayScreen(app, pool[:6], lambda *a, **k: None, 1, None, None, None)
    print("PLAY1  max_scroll:", play._max_scroll(),
          "viewport_h:", play._viewport().height,
          "content_h:", play._content_h())
    pygame.image.save(_render(app, play), str(out / "play_w1.png"))

    from src.game.replay_feed import ReplayFeed
    feed = ReplayFeed.from_file("assets/data/simulations/wc2018_final_fra_cro.json")
    big_pool = flow._pool_from_feed(feed)
    bigdraft = DraftScreen(app, big_pool, lambda *_: None, None)
    print("DRAFT22 max_scroll:", bigdraft._max_scroll(),
          "players:", len(big_pool))
    pygame.image.save(_render(app, bigdraft), str(out / "draft_22.png"))

    print("saved to", out)


if __name__ == "__main__":
    main()
