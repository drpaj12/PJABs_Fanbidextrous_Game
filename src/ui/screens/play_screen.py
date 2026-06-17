# src/ui/screens/play_screen.py
"""Play screen: window header + countdown, scrollable result log, prediction steppers.

on_submit(preds: list[Prediction], active_id: str, use_power: bool) fires on Lock.
The countdown is cosmetic in SIM/single-device play; it does not force submission.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, LogList, athlete_card, font
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_MAX = CONFIG["game"]["max_predictions_per_window"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]


class PlayScreen(Screen):
    def __init__(self, app: "App", available: list[DraftedAthlete],
                 on_submit: Callable[..., None], log: LogList, window: int,
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.log = log
        self.window = window
        self.sim = sim
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self.chosen: list[str] = []
        self.active_id: str | None = None
        self.use_power = False
        self.remaining = float(CONFIG["game"]["window_seconds"])
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.lock_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("play_lock_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("play_lock_btn_h", 56)),
            "Lock predictions")

    # -- geometry --
    def _stat_top(self) -> int:
        return LAYOUT.i("play_log_top", 100) + LAYOUT.i("play_log_h", 360) + 12

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        h = LAYOUT.i("play_stat_row_h", 52)
        return pygame.Rect(m, self._stat_top() + i * (h + 6),
                           self.app.screen.get_width() - 2 * m, h)

    def _player_rect(self, j: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        base = self._stat_top() + len(_STATS) * (LAYOUT.i("play_stat_row_h", 52) + 6) + 8
        return pygame.Rect(m, base + j * 60, self.app.screen.get_width() - 2 * m, 52)

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        self.log.handle(event)
        if self.sim and self.sim.is_key(event, pygame.K_a):
            self._auto_pick()
            return
        if self.sim and self.sim.is_key(event, pygame.K_f):
            self._auto_pick()
            self._submit()
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            if r.collidepoint(event.pos):
                if event.pos[0] > r.right - 56:
                    self.lines[s["code"]] += 1
                elif event.pos[0] > r.right - 112:
                    self.lines[s["code"]] = max(0, self.lines[s["code"]] - 1)
                else:
                    self._toggle(s["code"])
                return
        for j, ath in enumerate(self.available):
            if self._player_rect(j).collidepoint(event.pos):
                self.active_id = ath.athlete_id
                return
        if self.lock_btn.hit(event.pos):
            self._submit()

    def _toggle(self, code: str) -> None:
        if code in self.chosen:
            self.chosen.remove(code)
        elif len(self.chosen) < _MAX:
            self.chosen.append(code)

    def _auto_pick(self) -> None:
        self.chosen = [s["code"] for s in _STATS[:_MAX]]
        self.active_id = self.available[0].athlete_id

    def _submit(self) -> None:
        if self.chosen and self.active_id:
            preds = [Prediction(c, self.lines[c]) for c in self.chosen]
            self.on_submit(preds, self.active_id, self.use_power)

    def update(self, dt: float) -> None:
        self.remaining = max(0.0, self.remaining - dt)

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        hf = font(LAYOUT.i("play_window_size", 20))
        surface.blit(hf.render(f"Window {self.window}", True, _C["text_dim"]), (m, 16))
        tf = font(LAYOUT.i("play_timer_size", 30))
        mm, ss = divmod(int(self.remaining), 60)
        surface.blit(tf.render(f"{mm}:{ss:02d}", True, _C["accent"]), (m, 44))
        self.log.draw(surface)
        sf = font(LAYOUT.i("play_stat_size", 20))
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            sel = s["code"] in self.chosen
            pygame.draw.rect(surface, _C["accent"] if sel else _C["surface"], r, border_radius=8)
            surface.blit(sf.render(f"{s['label']}: {self.lines[s['code']]}", True, _C["white"]),
                         (r.x + 8, r.y + 14))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 12))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 12))
        for j, ath in enumerate(self.available):
            athlete_card(surface, self._player_rect(j), sf, ath.name, ath.archetype,
                         ath.stars, ath.athlete_id == self.active_id)
        self.lock_btn.draw(surface, sf)
