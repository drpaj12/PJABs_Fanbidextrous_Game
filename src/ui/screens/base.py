# src/ui/screens/base.py
"""Base screen for the async state machine."""
import pygame


class Screen:
    def __init__(self, app: "object") -> None:
        self.app = app

    def handle(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
