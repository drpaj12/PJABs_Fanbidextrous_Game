"""Web-compatible entry point for pygbag.

pygbag requires:
1. A main.py at the package root
2. An async main loop with `await asyncio.sleep(0)` each frame
3. The game loop cannot use sys.exit()

Usage:
    pygbag .                    # serve from project root
    pygbag --build .            # build for deployment
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

import pygame

# All imports at top level — Python 3.12 (pygbag CDN) scoping
# requires this to avoid "cannot access local variable" errors
from src.ui.game_window import run


async def main():
  try:
    await run()

  except Exception as e:
    import traceback
    print(f"FATAL ERROR: {e}")
    traceback.print_exc()
    try:
        screen = pygame.display.get_surface()
        if screen:
            screen.fill((200, 50, 50))
            font = pygame.font.Font(None, 36)
            err_text = font.render(f"ERROR: {e}", True, (255, 255, 255))
            screen.blit(err_text, (50, 50))
            # Show traceback lines on screen
            tb_lines = traceback.format_exc().split("\n")
            small = pygame.font.Font(None, 22)
            for i, line in enumerate(tb_lines[-8:]):
                surf = small.render(line[:100], True, (255, 200, 200))
                screen.blit(surf, (50, 100 + i * 24))
            pygame.display.flip()
    except Exception:
        pass
    while True:
        await asyncio.sleep(1)


asyncio.run(main())
