# src/ui/app.py
"""Async pygame app + screen state machine. pygbag entry path."""
import asyncio
import time
import pygame
from src.utils.constants import CONFIG, LAYOUT
from src.utils.build_info import build_id
from src.ui.widgets import font

_D = CONFIG["display"]
_C = CONFIG["colors"]


class App:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((_D["width"], _D["height"]))
        pygame.display.set_caption(_D["title"])
        self.clock = pygame.time.Clock()
        self.font = font(22)
        self.running = True
        self.current = None  # set by set_screen
        self.overlay = None          # callable(surface) drawn on top each frame
        self.global_handler = None   # callable(event) -> bool, consumes before screen
        # Build stamp: the apk basename, drawn tiny at the bottom of every screen so a
        # stale browser cache is obvious at a glance. Rendered once -- it never changes.
        f = font(LAYOUT.i("build_stamp_size", 12))
        self._build_stamp = f.render(build_id(), True, _C["text_dim"])
        # Wall clock: current local time, drawn top-right on every screen. Re-rendered each
        # frame (the string changes), so cache only the Font object, not a surface.
        self._clock_font = font(LAYOUT.i("wall_clock_size", 14))

    def set_screen(self, screen) -> None:
        self.current = screen

    async def run(self) -> None:
        while self.running:
            dt = self.clock.tick(_D["fps"]) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif self.current is not None:
                    if not (self.global_handler and self.global_handler(event)):
                        self.current.handle(event)
            if self.current is not None:
                self.current.update(dt)
            self.screen.fill(_C["background"])
            if self.current is not None:
                self.current.draw(self.screen)
            if self.overlay is not None:
                self.overlay(self.screen)
            self._draw_build_stamp()
            self._draw_wall_clock()
            pygame.display.flip()
            await asyncio.sleep(0)

    def _draw_build_stamp(self) -> None:
        """Blit the build id at the bottom centre, just inside the edge."""
        margin = LAYOUT.i("build_stamp_margin", 4)
        rect = self._build_stamp.get_rect()
        rect.midbottom = (_D["width"] // 2, _D["height"] - margin)
        self.screen.blit(self._build_stamp, rect)

    def _draw_wall_clock(self) -> None:
        """Blit the current local wall-clock time (HH:MM:SS) at the top-right of every
        screen, so both co-op players share an at-a-glance real-time reference."""
        margin = LAYOUT.i("wall_clock_margin", 6)
        surf = self._clock_font.render(time.strftime("%H:%M:%S"), True, _C["text_dim"])
        rect = surf.get_rect()
        rect.topright = (_D["width"] - margin, margin)
        self.screen.blit(surf, rect)
