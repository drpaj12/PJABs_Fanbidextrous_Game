# src/ui/app.py
"""Async pygame app + screen state machine. pygbag entry path."""
import asyncio
import pygame
from src.utils.constants import CONFIG

_D = CONFIG["display"]
_C = CONFIG["colors"]


class App:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((_D["width"], _D["height"]))
        pygame.display.set_caption(_D["title"])
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 22)
        self.running = True
        self.current = None  # set by set_screen

    def set_screen(self, screen) -> None:
        self.current = screen

    async def run(self) -> None:
        while self.running:
            dt = self.clock.tick(_D["fps"]) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif self.current is not None:
                    self.current.handle(event)
            if self.current is not None:
                self.current.update(dt)
            self.screen.fill(_C["background"])
            if self.current is not None:
                self.current.draw(self.screen)
            pygame.display.flip()
            await asyncio.sleep(0)
