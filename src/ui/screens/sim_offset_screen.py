# src/ui/screens/sim_offset_screen.py
"""Realtime SIM harness: choose the JOIN OFFSET (minutes relative to kickoff) before the
rehearsal starts. -5 = five minutes before kickoff; +5 = the 5th minute; +20 = the 20th
minute (after window 1 has already played). A big +/- stepper sets the offset; START runs
the crawl on the virtual clock from that point. Pure routing + rendering -- the clock math
lives in src/game/sim_clock.py.

SIM auto-starts with the default offset when SIM mode is enabled, so a headless/demo path
keeps moving; a normal (taps) run waits for the dev to dial in an offset and press START.
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
_H = CONFIG["sim_harness"]


def _fmt_offset(minutes: int) -> str:
    """+20 / -5 / 0 (kickoff). ASCII only."""
    if minutes == 0:
        return "0 (kickoff)"
    return f"{'+' if minutes > 0 else '-'}{abs(minutes)}"


class SimOffsetScreen(Screen):
    def __init__(self, app: "App", mode_label: str, game_label: str,
                 on_start: Callable[[int], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.mode_label = mode_label
        self.game_label = game_label
        self.on_start = on_start
        self.sim = sim
        self._started = False
        self.offset = int(_H["offset_default"])
        self._min = int(_H["offset_min"])
        self._max = int(_H["offset_max"])
        self._step = int(_H["offset_step"])
        sw, sh = app.screen.get_size()
        bw = LAYOUT.i("fixsel_btn_w", 360)
        cx = sw // 2
        row_y = LAYOUT.i("simoff_stepper_y", 300)
        sz = LAYOUT.i("simoff_step_btn", 72)
        self.minus_btn = Button(pygame.Rect(cx - bw // 2, row_y, sz, sz), "-")
        self.plus_btn = Button(pygame.Rect(cx + bw // 2 - sz, row_y, sz, sz), "+")
        self.start_btn = Button(
            pygame.Rect(cx - bw // 2, LAYOUT.i("simoff_start_y", 440), bw,
                        LAYOUT.i("fixsel_btn_h", 72)), "START")

    def _adjust(self, delta: int) -> None:
        self.offset = max(self._min, min(self._max, self.offset + delta))

    def handle(self, event: pygame.event.Event) -> None:
        if self._started or event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.minus_btn.hit(event.pos):
            self._adjust(-self._step)
        elif self.plus_btn.hit(event.pos):
            self._adjust(self._step)
        elif self.start_btn.hit(event.pos):
            self._start()

    def _start(self) -> None:
        if not self._started:
            self._started = True
            self.on_start(self.offset)

    def update(self, dt: float) -> None:
        if self._started or not (self.sim and self.sim.enabled):
            return
        self._start()                    # headless/demo: run straight through at default offset

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render("Join offset", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))
        sf = font(LAYOUT.i("ui_small_size", 17))
        sub = sf.render(f"{self.mode_label}   {self.game_label}", True, _C["accent"])
        surface.blit(sub, sub.get_rect(center=(sw // 2, LAYOUT.i("fixsel_sub_y", 200))))

        bf = font(LAYOUT.i("ui_body_size", 22))
        self.minus_btn.draw(surface, bf)
        self.plus_btn.draw(surface, bf)
        vf = font(LAYOUT.i("simoff_value_size", 40))
        vimg = vf.render(_fmt_offset(self.offset), True, _C["white"])
        surface.blit(vimg, vimg.get_rect(
            center=(sw // 2, self.minus_btn.rect.centery)))
        self.start_btn.draw(surface, bf)

        hint = font(LAYOUT.i("ui_small_size", 17))
        msg = ("-5 = 5 min before kickoff   +20 = 20th minute (after window 1)")
        h = hint.render(msg, True, _C["text_dim"])
        surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 50)))
