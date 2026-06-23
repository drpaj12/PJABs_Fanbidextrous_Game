# src/ui/screens/party_play_screen.py
"""One window of the cooperative crawl on this member's device.

Phase 'edit': five dials + Submit -> coordinator.submit_pick. Phase 'wait': poll the relay;
the leader also tries to resolve (require_all unless the flow forces a boundary) and runs an
optional on_poll hook (LIVE feed fetch+share). Phase 'resolved': render the pushed depth/colors/
log + live scoreline + Continue. Resolution authority lives on the leader, never here."""
import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import (Button, LogList, draw_depth_meter, draw_match_banner,
                            font, wall_clock_str, wrap_text)
from src.ui.sim import SimMode
from src.sync.party_coordinator import PartyCoordinator
from src.game.dungeon import gate_step, monster_flavor
from src.game.window_resolver import build_stat_results
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_POLL = float(CONFIG["party"]["poll_seconds"])


class PartyPlayScreen(Screen):
    def __init__(self, app: "App", coord: PartyCoordinator, window: int, label: str,
                 on_continue: Callable[[], None], require_all: bool = True,
                 on_poll: Optional[Callable[[], Awaitable[None]]] = None,
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.coord = coord
        self.window = window
        self.label = label
        self.on_continue = on_continue
        self.require_all = require_all
        self.on_poll = on_poll
        self.sim = sim
        self.phase = "edit"
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self._polling = False
        self._elapsed = _POLL
        self._logged = 0
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.log = LogList(pygame.Rect(m, LAYOUT.i("dp_content_top", 92),
                                       sw - 2 * m, LAYOUT.i("dp_log_h", 150)))
        self.action_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dp_btn_h", 56) - 12, sw - 2 * m,
                        LAYOUT.i("dp_btn_h", 56)), "Submit picks")

    def _stat_step(self) -> int:
        return LAYOUT.i("dp_stat_row_h", 48) + LAYOUT.i("dp_stat_gap", 6)

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("dp_content_top", 92)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * self._stat_step(), w, LAYOUT.i("dp_stat_row_h", 48))

    def handle(self, event: pygame.event.Event) -> None:
        if self.phase == "edit":
            if self.sim and self.sim.is_key(event, pygame.K_f):
                self._submit()
                return
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
            if self.action_btn.hit(event.pos):
                self._submit()
                return
            for i, s in enumerate(_STATS):
                r = self._stat_rect(i)
                if r.collidepoint(event.pos):
                    self._tap_stat(s["code"], event.pos[0], r)
                    return
        elif self.phase == "resolved":
            self.log.handle(event)
            if event.type == pygame.MOUSEBUTTONDOWN and self.action_btn.hit(event.pos):
                self.on_continue()
            elif self.sim and self.sim.is_key(event, pygame.K_s):
                self.on_continue()

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:
            self.lines[code] += 1
        elif x > r.right - 112:
            self.lines[code] = max(0, self.lines[code] - 1)

    def _submit(self) -> None:
        asyncio.ensure_future(self.coord.submit_pick(self.window, dict(self.lines)))
        self.phase = "wait"

    def force_resolve(self) -> None:
        """Flow hook (LIVE): the match clock crossed this window's boundary. If still editing,
        auto-submit the current dials; the leader will resolve with require_all=False."""
        if self.phase == "edit":
            self._submit()
        self.require_all = False

    def update(self, dt: float) -> None:
        if self.phase == "edit":
            return
        self._elapsed += dt
        if not self._polling and self._elapsed >= _POLL:
            self._kick_poll()
        if self.phase == "wait" and self.coord.resolved_through() >= self.window:
            self._enter_resolved()

    def _kick_poll(self) -> None:
        self._polling = True
        self._elapsed = 0.0

        async def go() -> None:
            try:
                await self.coord.refresh()
                if self.on_poll is not None:
                    await self.on_poll()
                if self.coord.is_leader:
                    await self.coord.leader_try_resolve(self.window, self.require_all)
            finally:
                self._polling = False
        asyncio.ensure_future(go())

    def _enter_resolved(self) -> None:
        self.phase = "resolved"
        for line in self.coord.view()["log"][self._logged:]:
            self.log.add(line)
        self._logged = len(self.coord.view()["log"])
        self.action_btn.label = "Continue"

    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        v = self.coord.view()
        hf = font(LAYOUT.i("dp_header_size", 18))
        surface.blit(hf.render(self.label, True, _C["accent"]), (m, LAYOUT.i("dp_header_y", 14)))
        mt = v.get("match", {})
        if mt.get("home"):
            status = f" {mt['status']}" if mt.get("status") else ""
            score = (f"{mt.get('home','')} {mt.get('home_goals',0)}-{mt.get('away_goals',0)} "
                     f"{mt.get('away','')}  ({mt.get('minute',0)}'{status})")
        else:
            score = "Waiting for match data..."
        draw_match_banner(surface, score, LAYOUT.i("pplay_score_y", 38), wall_clock_str())
        stf = font(LAYOUT.i("dp_status_size", 16))
        status = f"Power {v['power']}   Wounds {v['wounds']}   My gold {self.coord.my_treasury()}"
        surface.blit(stf.render(status, True, _C["white"]), (m, LAYOUT.i("dp_status_y", 60)))
        if self.phase == "edit":
            self._draw_dials(surface)
            self._draw_flavor(surface, v)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))
        elif self.phase == "wait":
            wf = font(LAYOUT.i("pplay_wait_size", 20))
            msg = "Resolving..." if self.coord.is_leader else "Waiting for the party..."
            w = wf.render(msg, True, _C["accent"])
            surface.blit(w, w.get_rect(center=(surface.get_width() // 2,
                                               LAYOUT.i("pplay_wait_y", 420))))
        else:
            self._draw_resolved(surface, v)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))

    def _draw_dials(self, surface: pygame.Surface) -> None:
        sf = font(LAYOUT.i("dp_stat_size", 19))
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            surface.blit(sf.render(f"{s['label']}: {self.lines[s['code']]}", True, _C["white"]),
                         (r.x + 12, r.y + 12))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 10))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 10))

    def _draw_flavor(self, surface: pygame.Surface, v: dict) -> None:
        """Window flavor: how many monsters the party faces this descent."""
        size = max(1, len(v.get("members", [])))
        flavor = monster_flavor(self.coord.half(), size, int(v.get("threat", 0)))
        ff = font(LAYOUT.i("dp_flavor_size", 17))
        m = LAYOUT.i("screen_margin", 20)
        max_w = self.app.screen.get_width() - 2 * m
        y = self._stat_rect(len(_STATS) - 1).bottom + LAYOUT.i("dp_section_gap", 24)
        for line in wrap_text(flavor["text"], ff, max_w):
            surface.blit(ff.render(line, True, _C["orange"]), (m, y))
            y += LAYOUT.i("dp_flavor_line_gap", 24)

    def _draw_resolved(self, surface: pygame.Surface, v: dict) -> None:
        self.log.draw(surface)
        m = LAYOUT.i("screen_margin", 20)
        cells_y = self.log.rect.bottom + LAYOUT.i("dp_section_gap", 24)
        h, gap = LAYOUT.i("dp_cells_h", 28), LAYOUT.i("dp_cell_gap", 6)
        for i, key in enumerate(v["window_colors"]):
            cell = pygame.Rect(m + i * (h + gap), cells_y, h, h)
            pygame.draw.rect(surface, _C.get(key, _C["orange"]), cell, border_radius=6)
        meter_y = cells_y + h + LAYOUT.i("dp_section_gap", 24)
        color = v["window_colors"][-1] if v["window_colors"] else "orange"
        draw_depth_meter(surface, pygame.Rect(m, meter_y, surface.get_width() - 2 * m, 0),
                         v["depth"], v["total"], gate_step(self.coord.half()), color)
        meter_h = LAYOUT.i("depth_label_size", 14) + 4 + LAYOUT.i("depth_meter_h", 26)
        self._draw_results_strip(surface, v, m, meter_y + meter_h
                                 + LAYOUT.i("dp_section_gap", 24))

    def _draw_results_strip(self, surface: pygame.Surface, v: dict, x: int, y: int) -> None:
        """Per-prediction feedback for THIS player's own picks vs the leader-pushed actuals:
        'label: you P / was A' tinted green/orange/red, underlined when correct (green).
        Followers without pushed actuals fall back to the depth/colors view (no strip)."""
        actuals = v.get("actuals") or {}
        if not actuals:
            return
        rf = font(LAYOUT.i("dp_result_size", 17))
        gap = LAYOUT.i("dp_result_line_gap", 26)
        for sr in build_stat_results(self.lines, actuals):
            col = _C.get(sr.color_key, _C["orange"])
            img = rf.render(f"{sr.label}: you {sr.predicted} / was {sr.actual}", True, col)
            surface.blit(img, (x, y))
            if sr.color_key == "green":
                uy = y + img.get_height() + 1
                pygame.draw.line(surface, col, (x, uy), (x + img.get_width(), uy), 2)
            y += gap
