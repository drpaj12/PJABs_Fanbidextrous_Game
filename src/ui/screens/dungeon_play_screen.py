# src/ui/screens/dungeon_play_screen.py
"""One 15-minute window of the dungeon crawl, single device.

Phase 'predict': five stat dials with -/+ steppers and a Descend button -> on_descend(lines)
returns the resolved WindowResult. Phase 'resolved': the advanced depth meter, window-color
cells, Power / wounds / treasury, and the crawl log; a Continue button -> on_continue().

lines is a dict {goal, shot, corner, card, foul} of predicted lines for the (single-device)
party. SIM 'A' auto-fills defaults; 'F' auto-fills and descends."""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, LogList, draw_depth_meter, font, wrap_text
from src.ui.sim import SimMode
from src.game.crawl import CrawlSession
from src.game.dungeon import gate_step, monster_flavor
from src.game.window_resolver import WindowResult
from src.utils.asset_loader import load_icon
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_HALF_MIN = CONFIG["game"]["half_minutes"]


class DungeonPlayScreen(Screen):
    def __init__(self, app: "App", session: CrawlSession, feed,
                 window: int, label: str,
                 on_descend: Callable[[dict], WindowResult],
                 on_continue: Callable[[], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.session = session
        self.feed = feed
        self.window = window
        self.label = label
        self.on_descend = on_descend
        self.on_continue = on_continue
        self.sim = sim
        self.phase = "predict"
        self.result: Optional[WindowResult] = None
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.log = LogList(pygame.Rect(m, LAYOUT.i("dp_content_top", 92),
                                       sw - 2 * m, LAYOUT.i("dp_log_h", 150)))
        for line in session.log:
            self.log.add(line)
        self.action_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dp_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("dp_btn_h", 56)),
            "Descend")

    # -- geometry for the predict-phase stat rows --
    def _stat_step(self) -> int:
        return LAYOUT.i("dp_stat_row_h", 48) + LAYOUT.i("dp_stat_gap", 6)

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("dp_content_top", 92)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * self._stat_step(), w, LAYOUT.i("dp_stat_row_h", 48))

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.phase == "predict":
            if self.sim and self.sim.is_key(event, pygame.K_a):
                return  # defaults already set; nothing to change
            if self.sim and self.sim.is_key(event, pygame.K_f):
                self._descend()
                return
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
            if self.action_btn.hit(event.pos):
                self._descend()
                return
            for i, s in enumerate(_STATS):
                r = self._stat_rect(i)
                if r.collidepoint(event.pos):
                    self._tap_stat(s["code"], event.pos[0], r)
                    return
        else:  # resolved
            self.log.handle(event)
            if self.sim and self.sim.is_key(event, pygame.K_s):
                self.on_continue()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and self.action_btn.hit(event.pos):
                self.on_continue()

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:
            self.lines[code] += 1
        elif x > r.right - 112:
            self.lines[code] = max(0, self.lines[code] - 1)

    def _descend(self) -> None:
        self.result = self.on_descend(dict(self.lines))
        for line in self.result.log:
            self.log.add(line)
        self.phase = "resolved"
        self.action_btn.label = ("Continue" if not self.session.match_over()
                                 else "See results")

    def update(self, dt: float) -> None:
        ...

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        hf = font(LAYOUT.i("dp_header_size", 18))
        surface.blit(hf.render(self.label, True, _C["accent"]), (m, LAYOUT.i("dp_header_y", 14)))
        sf = font(LAYOUT.i("dp_score_size", 15))
        surface.blit(sf.render(self._match_line(), True, _C["text_dim"]),
                     (m, LAYOUT.i("dp_score_y", 38)))
        stf = font(LAYOUT.i("dp_status_size", 16))
        surface.blit(stf.render(self._status_line(), True, _C["white"]),
                     (m, LAYOUT.i("dp_status_y", 60)))
        if self.phase == "predict":
            self._draw_predict(surface)
        else:
            self._draw_resolved(surface)
        self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))

    def _match_line(self) -> str:
        meta = getattr(self.feed, "meta", {})
        home = meta.get("home_team", "Home")
        away = meta.get("away_team", "Away")
        minute = (self.session.half - 1) * _HALF_MIN + self.window * _WINDOW_MIN
        goals = self.feed.snapshot_at(minute).stats.get("goals", 0)
        return f"{home} v {away}   goals {goals} ({minute}')"

    def _status_line(self) -> str:
        st = self.session.state
        hearts = "<3" * max(0, int(CONFIG["dungeon"]["max_wounds"]) - st.wounds)
        return f"Power {st.power}   Wounds {st.wounds}   Gold {self.session.treasury}   {hearts}"

    def _draw_predict(self, surface: pygame.Surface) -> None:
        sf = font(LAYOUT.i("dp_stat_size", 19))
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            surface.blit(sf.render(f"{s['label']}: {self.lines[s['code']]}", True, _C["white"]),
                         (r.x + 12, r.y + 12))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 10))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 10))
        self._draw_flavor(surface, self._stat_rect(len(_STATS) - 1).bottom
                          + LAYOUT.i("dp_section_gap", 24))

    def _draw_flavor(self, surface: pygame.Surface, y: int) -> None:
        """Window flavor: how many monsters the party faces this descent."""
        st = self.session.state
        flavor = monster_flavor(st.half, st.party_size, st.threat)
        ff = font(LAYOUT.i("dp_flavor_size", 17))
        m = LAYOUT.i("screen_margin", 20)
        max_w = self.app.screen.get_width() - 2 * m
        for line in wrap_text(flavor["text"], ff, max_w):
            surface.blit(ff.render(line, True, _C["orange"]), (m, y))
            y += LAYOUT.i("dp_flavor_line_gap", 24)

    def _draw_resolved(self, surface: pygame.Surface) -> None:
        self.log.draw(surface)
        m = LAYOUT.i("screen_margin", 20)
        cells_y = self.log.rect.bottom + LAYOUT.i("dp_section_gap", 24)
        self._draw_window_cells(surface, m, cells_y)
        meter_y = cells_y + LAYOUT.i("dp_cells_h", 28) + LAYOUT.i("dp_section_gap", 24)
        draw_depth_meter(
            surface,
            pygame.Rect(m, meter_y, self.app.screen.get_width() - 2 * m, 0),
            self.session.state.depth, self.session.state.total_tiles,
            gate_step(self.session.half), self.result.color if self.result else "orange")
        meter_h = LAYOUT.i("depth_label_size", 14) + 4 + LAYOUT.i("depth_meter_h", 26)
        self._draw_results_strip(surface, m, meter_y + meter_h
                                 + LAYOUT.i("dp_section_gap", 24))

    def _draw_results_strip(self, surface: pygame.Surface, x: int, y: int) -> None:
        """Per-prediction feedback: 'label: you P / was A' tinted green/orange/red, with an
        underline under correct (green) predictions -- the dungeon's draft-style readout."""
        if not self.result or not self.result.stat_results:
            return
        rf = font(LAYOUT.i("dp_result_size", 17))
        gap = LAYOUT.i("dp_result_line_gap", 26)
        for sr in self.result.stat_results:
            col = _C.get(sr.color_key, _C["orange"])
            text = f"{sr.label}: you {sr.predicted} / was {sr.actual}"
            img = rf.render(text, True, col)
            surface.blit(img, (x, y))
            if sr.color_key == "green":
                uy = y + img.get_height() + 1
                pygame.draw.line(surface, col, (x, uy), (x + img.get_width(), uy), 2)
            y += gap

    def _draw_window_cells(self, surface: pygame.Surface, x: int, y: int) -> None:
        h = LAYOUT.i("dp_cells_h", 28)
        gap = LAYOUT.i("dp_cell_gap", 6)
        colors = self.session.window_colors
        for i, key in enumerate(colors):
            cell = pygame.Rect(x + i * (h + gap), y, h, h)
            pygame.draw.rect(surface, _C.get(key, _C["orange"]), cell, border_radius=6)
        icon = load_icon("monster")
        if icon is not None:
            surface.blit(pygame.transform.smoothscale(icon, (h, h)),
                         (self.app.screen.get_width() - x - h, y))
