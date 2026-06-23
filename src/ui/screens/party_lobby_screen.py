# src/ui/screens/party_lobby_screen.py
"""Party lobby: who has joined, and a wait for the leader to start. Polls the relay on the
party.poll_seconds rhythm. The leader sees a start button (action provided by the flow);
everyone advances when phase -> shop."""
import asyncio
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.sync.party_coordinator import PartyCoordinator
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_POLL = float(CONFIG["party"]["poll_seconds"])


class PartyLobbyScreen(Screen):
    def __init__(self, app: "App", coord: PartyCoordinator, on_start: Callable[[], None],
                 on_advance: Callable[[], None], start_label: str = "Start crawl",
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.coord = coord
        self.on_start = on_start
        self.on_advance = on_advance
        self.sim = sim
        self._polling = False
        self._elapsed = _POLL
        self._advanced = False
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.start_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("plobby_btn_h", 60) - 14, sw - 2 * m,
                        LAYOUT.i("plobby_btn_h", 60)), start_label)

    def handle(self, event: pygame.event.Event) -> None:
        if self.coord.is_leader and event.type == pygame.MOUSEBUTTONDOWN \
                and self.start_btn.hit(event.pos):
            self.on_start()

    def update(self, dt: float) -> None:
        if self._advanced:
            return
        self._elapsed += dt
        if not self._polling and self._elapsed >= _POLL:
            self._kick_poll()
        if self.sim and self.sim.enabled and self.coord.is_leader and self.coord.phase() == "lobby":
            self.on_start()
        if self.coord.phase() == "shop":
            self._advanced = True
            self.on_advance()

    def _kick_poll(self) -> None:
        self._polling = True
        self._elapsed = 0.0

        async def go() -> None:
            try:
                await self.coord.refresh()
            finally:
                self._polling = False
        asyncio.ensure_future(go())

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        m = LAYOUT.i("screen_margin", 20)
        tf = font(LAYOUT.i("plobby_title_size", 28))
        t = tf.render(f"Party {self.coord.party_id}", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("plobby_title_y", 90))))
        sf = font(LAYOUT.i("plobby_sub_size", 16))
        sub = sf.render(f"you are slot {self.coord.slot}", True, _C["text_dim"])
        surface.blit(sub, sub.get_rect(center=(sw // 2, LAYOUT.i("plobby_sub_y", 140))))
        rf = font(LAYOUT.i("plobby_row_size", 20))
        top = LAYOUT.i("plobby_row_top", 200)
        step = LAYOUT.i("plobby_row_h", 56) + LAYOUT.i("plobby_row_gap", 10)
        for i, (name, gold) in enumerate(self.coord.view()["members"]):
            r = pygame.Rect(m, top + i * step, sw - 2 * m, LAYOUT.i("plobby_row_h", 56))
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            tag = "  (leader)" if i == 0 else ""
            surface.blit(rf.render(f"{i}. {name}{tag}", True, _C["white"]), (r.x + 14, r.y + 16))
        if self.coord.is_leader:
            self.start_btn.draw(surface, font(LAYOUT.i("plobby_row_size", 20)))
        else:
            hf = font(LAYOUT.i("plobby_hint_size", 16))
            h = hf.render("Waiting for the leader...", True, _C["accent"])
            surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 60)))
