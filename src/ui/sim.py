# src/ui/sim.py
"""SIM mode: a flag plus hotkey constants and the help-popup state. Screens query it.

Hotkeys (only active when enabled):
  H  toggle the hotkey help popup
  R  auto-draft a full roster on a Draft screen
  A  auto-fill a valid prediction on a Play screen
  S  skip the current cinematic / advance the splash
  F  fast-forward the current window (auto-predict straight to the cinematic)
"""
import pygame
from src.ui.widgets import Popup

HELP_LINES = [
    "H  show / hide this help",
    "R  auto-draft 6 players",
    "A  auto-pick predictions",
    "S  skip animation / advance",
    "F  fast-forward this window",
]


class SimMode:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.show_help = False
        self._popup = Popup("SIM hotkeys", HELP_LINES)

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def is_key(self, event: pygame.event.Event, key: int) -> bool:
        """True if SIM is on and `event` is a keydown for `key`."""
        return (self.enabled and event.type == pygame.KEYDOWN and event.key == key)

    def handle_global(self, event: pygame.event.Event) -> bool:
        """Handle H (and dismiss-on-tap when help is open). Returns True if consumed."""
        if not self.enabled:
            return False
        if self.is_key(event, pygame.K_h):
            self.toggle_help()
            return True
        if self.show_help and event.type == pygame.MOUSEBUTTONDOWN:
            self.show_help = False
            return True
        return False

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if self.enabled and self.show_help:
            self._popup.draw(surface)
