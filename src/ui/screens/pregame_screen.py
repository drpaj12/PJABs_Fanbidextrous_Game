# src/ui/screens/pregame_screen.py
"""Pre-game lobby: shows the fixture and a Start button, then proceeds to the draft.

`fixture` is a dict with keys: home, away, competition, label. on_start() fires when
the player taps Start (or automatically once in SIM mode).
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


class PregameScreen(Screen):
    def __init__(self, app: "App", fixture: dict, on_start: Callable[..., None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.fixture = fixture
        self.on_start = on_start
        self.sim = sim
        self._advanced = False
        sw = app.screen.get_width()
        bw = LAYOUT.i("pregame_btn_w", 320)
        bh = LAYOUT.i("pregame_btn_h", 64)
        x = (sw - bw) // 2
        self.start_btn = Button(
            pygame.Rect(x, LAYOUT.i("pregame_btn_y", 700), bw, bh),
            CONFIG["pregame"]["start_button_label"])

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and self.start_btn.hit(event.pos):
            self.on_start()

    def update(self, dt: float) -> None:
        if self.sim and self.sim.enabled and not self.sim.show_help and not self._advanced:
            self._advanced = True
            self.on_start()

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("pregame_title_size", 30))
        t = tf.render(self.fixture["competition"], True, _C["accent"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("pregame_title_y", 140))))
        lf = font(LAYOUT.i("pregame_line_size", 22))
        gap = LAYOUT.i("pregame_line_gap", 40)
        y = LAYOUT.i("pregame_lines_y", 300)
        rows = (self.fixture["home"], "vs", self.fixture["away"], self.fixture["label"])
        for i, text in enumerate(rows):
            col = _C["text_dim"] if i == 1 else _C["white"]
            line = lf.render(text, True, col)
            surface.blit(line, line.get_rect(center=(sw // 2, y + i * gap)))
        self.start_btn.draw(surface, lf)
