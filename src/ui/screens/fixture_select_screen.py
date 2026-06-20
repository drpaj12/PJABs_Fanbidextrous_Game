# src/ui/screens/fixture_select_screen.py
"""Pick which live match to play. One button per configured fixture.

on_pick(fixture_id: int) fires when a match is tapped. In SIM the first fixture is
auto-picked so the headless/demo path keeps moving.
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
_COMP = CONFIG["live"]["competition_label"]


class FixtureSelectScreen(Screen):
    def __init__(self, app: "App", fixtures: list[dict],
                 on_pick: Callable[[int], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.fixtures = fixtures
        self.on_pick = on_pick
        self.sim = sim
        self._picked = False
        sw = app.screen.get_width()
        bw = LAYOUT.i("fixsel_btn_w", 360)
        bh = LAYOUT.i("fixsel_btn_h", 72)
        gap = LAYOUT.i("fixsel_btn_gap", 20)
        y0 = LAYOUT.i("fixsel_btn_y", 320)
        x = (sw - bw) // 2
        self.buttons = [
            (Button(pygame.Rect(x, y0 + i * (bh + gap), bw, bh), f["label"]), int(f["id"]))
            for i, f in enumerate(fixtures)
        ]

    def handle(self, event: pygame.event.Event) -> None:
        if self._picked or event.type != pygame.MOUSEBUTTONDOWN:
            return
        for btn, fid in self.buttons:
            if btn.hit(event.pos):
                self._pick(fid)
                return

    def _pick(self, fixture_id: int) -> None:
        if not self._picked:
            self._picked = True
            self.on_pick(fixture_id)

    def update(self, dt: float) -> None:
        if self.sim and self.sim.enabled and not self._picked and self.buttons:
            self._pick(self.buttons[0][1])

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render("Pick a live match", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))
        sf = font(LAYOUT.i("ui_body_size", 22))
        s = sf.render(_COMP, True, _C["accent"])
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i("fixsel_sub_y", 200))))
        bf = font(LAYOUT.i("ui_body_size", 22))
        for btn, _fid in self.buttons:
            btn.draw(surface, bf)
        hint = font(LAYOUT.i("ui_small_size", 17))
        h = hint.render("draft + first picks happen while the half is live", True, _C["text_dim"])
        surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 50)))
