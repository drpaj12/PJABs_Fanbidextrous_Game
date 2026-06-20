# src/ui/screens/fixture_select_screen.py
"""Dynamic live-match picker: a scrollable list of curated games, soonest-first, each
showing its US Eastern kickoff and a 'how soon' status chip. Tapping a not-yet-finished
game enters the live flow via on_pick(game.id); finished games are greyed and untappable.

All time logic lives in src.game.schedule (pure). This file only renders + routes taps and
recomputes the visible set each frame from an injected now_fn, so relative labels stay live.
SIM auto-picks the first playable visible game so the headless/demo path keeps moving.
"""
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import ScrollButtons, font
from src.ui.sim import SimMode
from src.game.schedule import (ScheduledGame, visible_games, status_label,
                               game_status, is_playable)
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]


class FixtureSelectScreen(Screen):
    def __init__(self, app: "App", games: list[ScheduledGame],
                 on_pick: Callable[[int], None], cfg: dict,
                 sim: Optional[SimMode] = None,
                 now_fn: Callable[[], float] = time.time) -> None:
        super().__init__(app)
        self.games = games
        self.on_pick = on_pick
        self.cfg = cfg
        self.sim = sim
        self.now_fn = now_fn
        self._picked = False
        self.scroll = 0
        self._live_window = int(cfg["live_window_minutes"])
        self._soon = int(cfg["soon_minutes"])
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- which games show right now (rolling window, soonest-first) --
    def _visible(self) -> list[ScheduledGame]:
        return visible_games(self.games, self.now_fn(), self.cfg)

    # -- layout: the list scrolls inside a viewport below the title --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("fixsel_list_top", 210)
        bottom = self.app.screen.get_height() - LAYOUT.i("fixsel_list_bottom_pad", 60)
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _card_h(self) -> int:
        return LAYOUT.i("fixsel_card_h", 76)

    def _card_gap(self) -> int:
        return LAYOUT.i("fixsel_card_gap", 10)

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
        visible = self._visible()
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self._max_scroll(len(visible)),
                                     self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll,
                                                  self._max_scroll(len(visible)))
            return
        now = self.now_fn()
        for i, game in enumerate(visible):
            if not is_playable(game, now, self._live_window):
                continue
            if self._card_rect(i).collidepoint(event.pos):
                self._pick(game.id)
                return

    def _pick(self, fixture_id: int) -> None:
        if not self._picked:
            self._picked = True
            self.on_pick(fixture_id)

    def update(self, dt: float) -> None:
        if self._picked or not (self.sim and self.sim.enabled):
            return
        now = self.now_fn()
        for game in self._visible():
            if is_playable(game, now, self._live_window):
                self._pick(game.id)
                return

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render("Pick a live match", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))

        visible = self._visible()
        if not visible:
            self._draw_empty(surface)
            return

        now = self.now_fn()
        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        for i, game in enumerate(visible):
            r = self._card_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            self._draw_card(surface, r, game, now)
        surface.set_clip(prev)

        max_scroll = self._max_scroll(len(visible))
        if max_scroll > 0:
            self.scroll_btns.draw(surface, self.scroll, max_scroll)

    def _draw_empty(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        f = font(LAYOUT.i("ui_body_size", 22))
        msg = f.render("No games scheduled right now -- check back later", True,
                       _C["text_dim"])
        surface.blit(msg, msg.get_rect(center=(sw // 2, sh // 2)))

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect,
                   game: ScheduledGame, now: float) -> None:
        status = game_status(game, now, self._live_window)
        playable = status != "final"
        radius = LAYOUT.i("ui_corner_radius", 10)
        bg = _C["surface"] if playable else _C["background"]
        pygame.draw.rect(surface, bg, rect, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)

        title_col = _C["white"] if playable else _C["text_dim"]
        nmax = LAYOUT.i("fixsel_card_title_max", 26)
        nf = font(LAYOUT.i("fixsel_card_title_size", 22))
        surface.blit(nf.render(game.short_title()[:nmax], True, title_col),
                     (rect.x + 12, rect.y + 10))
        sf = font(LAYOUT.i("fixsel_card_sub_size", 17))
        surface.blit(sf.render(game.kickoff_local, True, _C["text_dim"]),
                     (rect.x + 12, rect.y + 42))

        chip = status_label(game, now, self._soon, self._live_window)
        chip_col = {"live": _C["accent"], "upcoming": _C["text"],
                    "final": _C["text_dim"]}[status]
        cf = font(LAYOUT.i("fixsel_chip_size", 18))
        chip_surf = cf.render(chip, True, chip_col)
        surface.blit(chip_surf,
                     chip_surf.get_rect(midright=(rect.right - 14, rect.centery)))
