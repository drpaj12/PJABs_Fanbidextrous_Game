# src/ui/screens/room.py
"""Room screen: Create Room or Join Room. In SIM mode auto-creates and proceeds.

on_done(room_code: str) is called when a room is created/joined.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]


class RoomScreen(Screen):
    def __init__(self, app: "App", on_done: Callable[..., None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.on_done = on_done
        self.sim = sim
        sw = app.screen.get_width()
        bw = LAYOUT.i("room_btn_w", 320)
        bh = LAYOUT.i("room_btn_h", 64)
        gap = LAYOUT.i("room_btn_gap", 24)
        y = LAYOUT.i("room_btn_y", 360)
        x = (sw - bw) // 2
        self.create_btn = Button(pygame.Rect(x, y, bw, bh), "Create Room")
        self.join_btn = Button(pygame.Rect(x, y + bh + gap, bw, bh), "Join Room")
        self.code = ""
        if sim and sim.enabled:
            sim.show_help = True          # reminder popup on entry (decision 4b)

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.create_btn.hit(event.pos):
                self.on_done("ROOM1")
            elif self.join_btn.hit(event.pos):
                self.on_done("ROOM1")     # single-device: join resolves to same room

    def update(self, dt: float) -> None:
        # SIM: auto-create and proceed once the help reminder is dismissed.
        if self.sim and self.sim.enabled and not self.sim.show_help and not self.code:
            self.code = "SIM01"
            self.on_done(self.code)

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("room_title_size", 34))
        t = tf.render("Co-op Room", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("room_title_y", 120))))
        bf = font(LAYOUT.i("ui_body_size", 22))
        self.create_btn.draw(surface, bf)
        self.join_btn.draw(surface, bf)
