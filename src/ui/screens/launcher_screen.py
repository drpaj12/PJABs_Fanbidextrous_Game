# src/ui/screens/launcher_screen.py
"""Web entry menu: one button per mode. The action fires when a button is tapped.

This is the first screen in the browser build so a tester can pick an offline
simulated game instead of waiting for a live match. Each option is a (label, action)
pair; the action takes over the screen (e.g. start the live picker or a sim).
"""
from typing import TYPE_CHECKING, Callable

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_TITLE = CONFIG["display"]["title"]


class LauncherScreen(Screen):
    def __init__(self, app: "App",
                 options: list[tuple[str, Callable[[], None]]]) -> None:
        super().__init__(app)
        self.options = options
        self._chosen = False
        sw = app.screen.get_width()
        bw = LAYOUT.i("fixsel_btn_w", 360)
        bh = LAYOUT.i("fixsel_btn_h", 72)
        gap = LAYOUT.i("fixsel_btn_gap", 20)
        y0 = LAYOUT.i("fixsel_btn_y", 320)
        x = (sw - bw) // 2
        self.buttons = [
            (Button(pygame.Rect(x, y0 + i * (bh + gap), bw, bh), label), action)
            for i, (label, action) in enumerate(options)
        ]

    def handle(self, event: pygame.event.Event) -> None:
        if self._chosen or event.type != pygame.MOUSEBUTTONDOWN:
            return
        for btn, action in self.buttons:
            if btn.hit(event.pos):
                self._chosen = True
                action()
                return

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render(_TITLE, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))
        sf = font(LAYOUT.i("ui_body_size", 22))
        s = sf.render("Choose a mode", True, _C["accent"])
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i("fixsel_sub_y", 200))))
        bf = font(LAYOUT.i("ui_body_size", 22))
        for btn, _action in self.buttons:
            btn.draw(surface, bf)
        hint = font(LAYOUT.i("ui_small_size", 17))
        h = hint.render("Test game replays a recorded match -- no live game needed",
                        True, _C["text_dim"])
        surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 50)))
