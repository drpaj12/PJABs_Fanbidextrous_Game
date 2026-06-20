# src/ui/screens/draft_screen.py
"""Draft: tap a card to zoom its detail; the Select button confirms it into the hand.

Mobile-first: full-width rows, large touch targets, a zoom panel for the tapped card.
SIM 'R' auto-drafts roster_size athletes and locks.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import athlete_card, Button, PlayerDetail, ScrollButtons, font
from src.game.athlete import DraftedAthlete
from src.game.ability_text import card_tagline
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_ROSTER_SIZE = CONFIG["game"]["roster_size"]
_C = CONFIG["colors"]


class DraftScreen(Screen):
    def __init__(self, app: "App", pool: list[DraftedAthlete],
                 on_lock: Callable[..., None], sim: Optional[SimMode] = None,
                 title: str = "Draft your six") -> None:
        super().__init__(app)
        self.pool = pool
        self.on_lock = on_lock
        self.sim = sim
        self.title = title
        self.selected: list[str] = []
        self.scroll = 0
        self.zoom_idx: int | None = None
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.lock_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("draft_lock_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("draft_lock_btn_h", 56)),
            f"Lock 0/{_ROSTER_SIZE}")
        self.detail = PlayerDetail(pygame.Rect(m, 120, sw - 2 * m, sh - 240))
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- layout: card list scrolls inside a viewport between the title and Lock --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("draft_list_top", 80)
        bottom = self.lock_btn.rect.top - 8
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _max_scroll(self) -> int:
        h = LAYOUT.i("draft_card_h", 64)
        gap = LAYOUT.i("draft_card_gap", 8)
        content_h = len(self.pool) * (h + gap)
        return max(0, content_h - self._viewport().height)

    def _card_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        h = LAYOUT.i("draft_card_h", 64)
        gap = LAYOUT.i("draft_card_gap", 8)
        top = LAYOUT.i("draft_list_top", 80)
        w = self.app.screen.get_width() - 2 * m - ScrollButtons.gutter()
        return pygame.Rect(m, top + i * (h + gap) - self.scroll, w, h)

    def _card_at(self, pos: tuple[int, int]) -> Optional[int]:
        for i in range(len(self.pool)):
            if self._card_rect(i).collidepoint(pos):
                return i
        return None

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_r):
            self.selected = [a.athlete_id for a in self.pool[:_ROSTER_SIZE]]
            self.on_lock(list(self.selected))
            return
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.zoom_idx is not None:
            if self.detail.select_btn.hit(event.pos):
                self._confirm(self.pool[self.zoom_idx].athlete_id)
            self.zoom_idx = None     # any tap (except a Select, handled above) closes
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll, self._max_scroll())
            return
        if self.lock_btn.hit(event.pos) and len(self.selected) == _ROSTER_SIZE:
            self.on_lock(list(self.selected))
            return
        idx = self._card_at(event.pos)
        if idx is not None:
            self.zoom_idx = idx

    def _confirm(self, aid: str) -> None:
        if aid in self.selected:
            self.selected.remove(aid)
        elif len(self.selected) < _ROSTER_SIZE:
            self.selected.append(aid)

    def update(self, dt: float) -> None:
        self.lock_btn.label = f"Lock {len(self.selected)}/{_ROSTER_SIZE}"

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        tf = font(LAYOUT.i("draft_name_size", 22) + 4)
        surface.blit(tf.render(self.title, True, _C["white"]),
                     (LAYOUT.i("screen_margin", 20), 30))
        cf = font(LAYOUT.i("draft_name_size", 22))
        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        for i, ath in enumerate(self.pool):
            r = self._card_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            athlete_card(surface, r, cf, ath.name, ath.archetype, ath.stars,
                         ath.athlete_id in self.selected, tagline=card_tagline(ath))
        surface.set_clip(prev)
        if self.zoom_idx is None and self._max_scroll() > 0:
            self.scroll_btns.draw(surface, self.scroll, self._max_scroll())
        self.lock_btn.draw(surface, cf)
        if self.zoom_idx is not None:
            self.detail.select_btn.label = (
                "Remove" if self.pool[self.zoom_idx].athlete_id in self.selected
                else "Select")
            self.detail.draw(surface, self.pool[self.zoom_idx])
