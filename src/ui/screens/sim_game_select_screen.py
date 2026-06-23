# src/ui/screens/sim_game_select_screen.py
"""Recorded-simulation picker: a scrollable list of bundled offline matches, each showing
its title and a subtitle (e.g. the round). Tapping a row enters the chosen offline flow via
on_pick(rel_path). Mirrors FixtureSelectScreen's scroll/card pattern, minus the live time
logic -- every recorded game is always playable.

SIM auto-picks the first game so the headless/demo path keeps moving. The discovery itself
is pure (src.game.simulations); this file only renders + routes taps.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import ScrollButtons, font
from src.ui.sim import SimMode
from src.game.simulations import SimGame
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]


class SimGameSelectScreen(Screen):
    def __init__(self, app: "App", games: list[SimGame],
                 on_pick: Callable[[str], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.games = games
        self.on_pick = on_pick
        self.sim = sim
        self._picked = False
        self.scroll = 0
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- layout: the list scrolls inside a viewport below the title --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("simsel_list_top", 210)
        bottom = self.app.screen.get_height() - LAYOUT.i("simsel_list_bottom_pad", 60)
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _card_h(self) -> int:
        return LAYOUT.i("simsel_card_h", 84)

    def _card_gap(self) -> int:
        return LAYOUT.i("simsel_card_gap", 10)

    def _max_scroll(self, count: int) -> int:
        content_h = count * (self._card_h() + self._card_gap())
        return max(0, content_h - self._viewport().height)

    def _card_rect(self, i: int) -> pygame.Rect:
        vp = self._viewport()
        h = self._card_h()
        gap = self._card_gap()
        w = vp.width - ScrollButtons.gutter()
        return pygame.Rect(vp.x, vp.top + i * (h + gap) - self.scroll, w, h)

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self._picked:
            return
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(len(self.games)),
                                     self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll,
                                                  self._max_scroll(len(self.games)))
            return
        for i, game in enumerate(self.games):
            if self._card_rect(i).collidepoint(event.pos):
                self._pick(game.path)
                return

    def _pick(self, path: str) -> None:
        if not self._picked:
            self._picked = True
            self.on_pick(path)

    def update(self, dt: float) -> None:
        if self._picked or not (self.sim and self.sim.enabled) or not self.games:
            return
        self._pick(self.games[0].path)

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("simsel_title_size", 30))
        t = tf.render("Pick a game", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("simsel_title_y", 150))))

        if not self.games:
            self._draw_empty(surface)
            return

        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        for i, game in enumerate(self.games):
            r = self._card_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            self._draw_card(surface, r, game)
        surface.set_clip(prev)

        max_scroll = self._max_scroll(len(self.games))
        if max_scroll > 0:
            self.scroll_btns.draw(surface, self.scroll, max_scroll)

    def _draw_empty(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        f = font(LAYOUT.i("ui_body_size", 22))
        msg = f.render("No recorded games found", True, _C["text_dim"])
        surface.blit(msg, msg.get_rect(center=(sw // 2, sh // 2)))

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect,
                   game: SimGame) -> None:
        radius = LAYOUT.i("ui_corner_radius", 10)
        pygame.draw.rect(surface, _C["surface"], rect, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)

        nmax = LAYOUT.i("simsel_card_title_max", 30)
        nf = font(LAYOUT.i("simsel_card_title_size", 22))
        surface.blit(nf.render(game.title[:nmax], True, _C["white"]),
                     (rect.x + 12, rect.y + 12))
        if game.subtitle:
            sf = font(LAYOUT.i("simsel_card_sub_size", 16))
            surface.blit(sf.render(game.subtitle[:nmax], True, _C["text_dim"]),
                         (rect.x + 12, rect.y + 46))
