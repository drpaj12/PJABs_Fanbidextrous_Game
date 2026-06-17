# src/ui/screens/cinematic_screen.py
"""Renders a CinematicScript: ticks, meter fills, explosions, shots, GOAL/CONCEDE.

Simple primitives only (rects, circles, lines, text). Tap or SIM 'S' skips. on_done()
fires exactly once when the script finishes (or is skipped).
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import MeterBar, font
from src.game.cinematic import (
    CinematicScript, TICK, METER, EXPLODE, SHOT, GOAL, CONCEDE, MISS, SUMMARY)
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_SUCCESS_THRESH = CONFIG["meter"]["success_threshold"]
_CONCEDE_THRESH = CONFIG["meter"]["concede_threshold"]

_DUR = {
    TICK: lambda: LAYOUT.f("cine_tick_dur", 0.55),
    METER: lambda: LAYOUT.f("cine_meter_dur", 0.5),
    EXPLODE: lambda: LAYOUT.f("cine_explode_dur", 0.6),
    SHOT: lambda: LAYOUT.f("cine_shot_dur", 0.7),
    GOAL: lambda: LAYOUT.f("cine_result_dur", 1.1),
    CONCEDE: lambda: LAYOUT.f("cine_result_dur", 1.1),
    MISS: lambda: LAYOUT.f("cine_result_dur", 1.1),
    SUMMARY: lambda: LAYOUT.f("cine_result_dur", 1.1),
}


class CinematicScreen(Screen):
    def __init__(self, app: "App", script: CinematicScript,
                 on_done: Callable[..., None], sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.script = script
        self.on_done = on_done
        self.sim = sim
        self.idx = 0
        self.t = 0.0
        self.done = False
        sw = app.screen.get_size()[0]
        m = LAYOUT.i("screen_margin", 20)
        mh = LAYOUT.i("cine_meter_h", 30)
        top = LAYOUT.i("cine_meter_top", 300)
        gap = LAYOUT.i("cine_meter_gap", 60)
        self.success_bar = MeterBar(pygame.Rect(m, top, sw - 2 * m, mh), _C["green"])
        self.concede_bar = MeterBar(pygame.Rect(m, top + gap, sw - 2 * m, mh), _C["red"])
        self.success_val = 0
        self.concede_val = 0
        self.success_disp = 0.0
        self.concede_disp = 0.0
        self.flash = 0.0          # 0..1 explode/result flash
        self.shake = 0

    @property
    def _beat(self):
        return self.script.beats[self.idx] if self.idx < len(self.script.beats) else None

    def _dur(self) -> float:
        b = self._beat
        return _DUR.get(b.kind, lambda: 0.5)() if b else 0.0

    def handle(self, event: pygame.event.Event) -> None:
        skip = (event.type == pygame.MOUSEBUTTONDOWN or
                (self.sim and self.sim.is_key(event, pygame.K_s)))
        if skip:
            self._skip()

    def _skip(self) -> None:
        # Apply every remaining meter value so the final bars read correctly.
        for b in self.script.beats[self.idx:]:
            if b.kind in (METER, EXPLODE):
                if b.meter == "success":
                    self.success_val = b.value
                elif b.meter == "concede":
                    self.concede_val = b.value
        self.success_disp = float(self.success_val)
        self.concede_disp = float(self.concede_val)
        self._finish()

    def _finish(self) -> None:
        if not self.done:
            self.done = True
            self.on_done()

    def _enter_beat(self) -> None:
        b = self._beat
        if b is None:
            return
        if b.kind == METER:
            if b.meter == "success":
                self.success_val = b.value
            else:
                self.concede_val = b.value
        elif b.kind == EXPLODE:
            self.flash = 1.0
            if b.meter == "success":
                self.success_val = 0
            else:
                self.concede_val = 0
        elif b.kind in (GOAL, CONCEDE):
            self.flash = 1.0
            self.shake = LAYOUT.i("cine_shake_px", 10)

    def update(self, dt: float) -> None:
        if self.done:
            return
        if self.t == 0.0:
            self._enter_beat()
        self.t += dt
        # ease displayed meter toward target
        self.success_disp += (self.success_val - self.success_disp) * min(1.0, dt * 8)
        self.concede_disp += (self.concede_val - self.concede_disp) * min(1.0, dt * 8)
        self.flash = max(0.0, self.flash - dt * 1.8)
        self.shake = max(0, self.shake - 1)
        if self.t >= self._dur():
            self.t = 0.0
            self.idx += 1
            if self.idx >= len(self.script.beats):
                self._finish()

    def draw(self, surface: pygame.Surface) -> None:
        ox = self.shake if (self.shake % 2 == 0) else -self.shake
        m = LAYOUT.i("screen_margin", 20)
        b = self._beat
        # result flash backdrop
        if self.flash > 0 and b and b.kind in (GOAL, EXPLODE):
            tint = _C["accent"] if (b.kind == GOAL or b.meter == "success") else _C["red"]
            fl = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            fl.fill((*tint, int(120 * self.flash)))
            surface.blit(fl, (0, 0))
        lf = font(LAYOUT.i("cine_label_size", 22))
        label_off = LAYOUT.i("cine_label_offset_y", 26)
        surface.blit(lf.render("Attack", True, _C["text_dim"]),
                     (m + ox, self.success_bar.rect.y - label_off))
        exp_s = self.flash if (b and b.kind == EXPLODE and b.meter == "success") else 0.0
        exp_c = self.flash if (b and b.kind == EXPLODE and b.meter == "concede") else 0.0
        self.success_bar.draw(surface, int(round(self.success_disp)), _SUCCESS_THRESH, exp_s)
        surface.blit(lf.render("Danger", True, _C["text_dim"]),
                     (m + ox, self.concede_bar.rect.y - label_off))
        self.concede_bar.draw(surface, int(round(self.concede_disp)), _CONCEDE_THRESH, exp_c)

        if b is None:
            return
        cx = surface.get_width() // 2
        if b.kind == TICK:
            txt = f"{b.label}: {b.detail.upper()}"
            color = _C["green"] if b.detail == "hit" else (
                _C["gold"] if b.detail == "near" else _C["red"])
            t = lf.render(txt, True, color)
            surface.blit(t, t.get_rect(center=(cx, LAYOUT.i("cine_tick_y", 200))))
        elif b.kind == SHOT:
            prog = min(1.0, self.t / max(0.01, self._dur()))
            r = LAYOUT.i("cine_shot_r", 16)
            sy = int(LAYOUT.i("cine_shot_start_y", 620)
                     - prog * LAYOUT.i("cine_shot_travel", 120))
            pygame.draw.circle(surface, _C["white"], (cx, sy), r)
            gw, gh = LAYOUT.i("cine_goal_box_w", 120), LAYOUT.i("cine_goal_box_h", 70)
            pygame.draw.rect(surface, _C["border"],
                             (cx - gw // 2, LAYOUT.i("cine_goalbox_y", 470), gw, gh), width=3)
            surface.blit(lf.render("SHOT!", True, _C["white"]),
                         lf.render("SHOT!", True, _C["white"]).get_rect(
                             center=(cx, LAYOUT.i("cine_shot_label_y", 660))))
        elif b.kind in (GOAL, CONCEDE, MISS):
            big = font(LAYOUT.i("cine_big_size", 64) if b.kind == GOAL
                       else LAYOUT.i("cine_label_size", 22)
                       + LAYOUT.i("cine_concede_size_delta", 14))
            color = _C["accent"] if b.kind == GOAL else (
                _C["red"] if b.kind == CONCEDE else _C["text_dim"])
            t = big.render(b.label, True, color)
            surface.blit(t, t.get_rect(center=(cx + ox, LAYOUT.i("cine_result_y", 440))))
        elif b.kind == SUMMARY:
            big = font(LAYOUT.i("cine_label_size", 22)
                       + LAYOUT.i("cine_summary_size_delta", 10))
            msg = f"+{self.script.team_delta} for / +{self.script.opp_delta} against"
            t = big.render(msg, True, _C["white"])
            surface.blit(t, t.get_rect(center=(cx, LAYOUT.i("cine_summary_y", 440))))
            surface.blit(lf.render("tap to continue", True, _C["text_dim"]),
                         (m, surface.get_height() - LAYOUT.i("cine_summary_hint_offset", 48)))
