# src/ui/screens/draft_screen.py
"""Draft screen: tap athlete cards to build a 6-athlete hand from the pool."""
import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import athlete_card, Button
from src.game.athlete import DraftedAthlete
from src.utils.constants import CONFIG

_ROSTER_SIZE = CONFIG["game"]["roster_size"]


class DraftScreen(Screen):
    def __init__(self, app, pool: list[DraftedAthlete], on_lock) -> None:
        super().__init__(app)
        self.pool = pool
        self.on_lock = on_lock
        self.selected: list[str] = []
        self.scroll = 0
        self.lock_btn = Button(pygame.Rect(20, app.screen.get_height() - 70,
                                           app.screen.get_width() - 40, 50),
                               f"Lock {len(self.selected)}/{_ROSTER_SIZE}")

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.lock_btn.hit(event.pos) and len(self.selected) == _ROSTER_SIZE:
                self.on_lock(list(self.selected))
                return
            idx = self._card_at(event.pos)
            if idx is not None:
                aid = self.pool[idx].athlete_id
                if aid in self.selected:
                    self.selected.remove(aid)
                elif len(self.selected) < _ROSTER_SIZE:
                    self.selected.append(aid)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 40)

    def _card_rect(self, i: int) -> pygame.Rect:
        return pygame.Rect(20, 20 + i * 70 - self.scroll, self.app.screen.get_width() - 40, 60)

    def _card_at(self, pos):
        for i in range(len(self.pool)):
            if self._card_rect(i).collidepoint(pos):
                return i
        return None

    def update(self, dt: float) -> None:
        self.lock_btn.label = f"Lock {len(self.selected)}/{_ROSTER_SIZE}"

    def draw(self, surface: pygame.Surface) -> None:
        for i, ath in enumerate(self.pool):
            r = self._card_rect(i)
            if r.bottom < 0 or r.top > surface.get_height():
                continue
            athlete_card(surface, r, self.app.font, ath.name, ath.archetype,
                         ath.stars, ath.athlete_id in self.selected)
        self.lock_btn.draw(surface, self.app.font)
