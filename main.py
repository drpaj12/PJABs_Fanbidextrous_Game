# main.py  (pygbag web entry)
import asyncio
import traceback

import pygame
from src.ui.app import App
from src.ui import flow


async def main() -> None:
    app = App()
    flow.start_app(app)   # username -> mode menu (live vs offline test game)
    await app.run()


def _show_crash(err: str) -> None:
    """Render a traceback to the canvas so a startup failure is readable, not a black
    page. Uses the built-in default font only (no system-font dependency)."""
    try:
        surface = pygame.display.get_surface() or pygame.display.set_mode((414, 896))
        surface.fill((20, 0, 0))
        f = pygame.font.Font(None, 20)
        title = pygame.font.Font(None, 28).render("Startup error", True, (255, 120, 120))
        surface.blit(title, (10, 10))
        lines: list[str] = []
        for raw in err.splitlines():
            while len(raw) > 56:
                lines.append(raw[:56]); raw = raw[56:]
            lines.append(raw)
        for i, line in enumerate(lines[-30:]):
            surface.blit(f.render(line, True, (255, 200, 200)), (10, 44 + i * 22))
        pygame.display.flip()
    except Exception:
        pass


async def _boot() -> None:
    try:
        await main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)          # also goes to the browser console
        _show_crash(tb)
        while True:         # keep the page alive so the message stays on screen
            await asyncio.sleep(0.2)


asyncio.run(_boot())
