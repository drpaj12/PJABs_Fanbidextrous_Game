# src/ui/screens/shop_screen.py
"""Dungeon shop: spend the shared party treasury on items generated from the live lineup.

Tap an unowned row to buy it (subject to slot / affordability / one-two-handed rules; the
reason shows inline on refusal). Tap an owned row to sell it back at full price. 'Descend'
enters the dungeon. SIM 'R' auto-buys the first affordable weapon + armor, then descends.

For SIM (single device) the whole party shares one loadout slot index (`member`), default 0.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, ScrollButtons, font
from src.ui.sim import SimMode
from src.game.crawl import CrawlSession
from src.utils.asset_loader import load_icon
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_HALF_LABEL = CONFIG["game"]["half_label"]
_SECOND_HALF_LABEL = CONFIG["game"]["second_half_label"]


class ShopScreen(Screen):
    def __init__(self, app: "App", session: CrawlSession,
                 on_done: Callable[[], None], sim: Optional[SimMode] = None,
                 member: int = 0) -> None:
        super().__init__(app)
        self.session = session
        self.on_done = on_done
        self.sim = sim
        self.member = member
        self.catalog = session.catalog()
        self.feedback = ""
        self.scroll = 0
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.done_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("shop_done_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("shop_done_btn_h", 56)),
            "Descend into the dungeon")
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- geometry --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("shop_list_top", 116)
        bottom = self.done_btn.rect.top - 8
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _row_step(self) -> int:
        return LAYOUT.i("shop_row_h", 64) + LAYOUT.i("shop_row_gap", 8)

    def _max_scroll(self) -> int:
        return max(0, len(self.catalog) * self._row_step() - self._viewport().height)

    def _row_rect(self, i: int) -> pygame.Rect:
        vp = self._viewport()
        w = vp.width - ScrollButtons.gutter()
        return pygame.Rect(vp.x, vp.top + i * self._row_step() - self.scroll,
                           w, LAYOUT.i("shop_row_h", 64))

    def _owned(self, item) -> bool:
        return any(it.item_id == item.item_id for it in self.session.loadouts[self.member].items)

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_r):
            self._auto_buy()
            self.on_done()
            return
        if event.type == pygame.MOUSEWHEEL:
            if self._viewport().collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll, self._max_scroll())
            return
        if self.done_btn.hit(event.pos):
            self.on_done()
            return
        if not self._viewport().collidepoint(event.pos):
            return
        for i, item in enumerate(self.catalog):
            if self._row_rect(i).collidepoint(event.pos):
                self._tap_item(item)
                return

    def _tap_item(self, item) -> None:
        if self._owned(item):
            self.session.sell(self.member, item.item_id)
            self.feedback = f"Sold {item.name} (+{item.price}g)"
        else:
            ok, reason = self.session.buy(self.member, item)
            self.feedback = (f"Bought {item.name} (-{item.price}g)" if ok
                             else f"Cannot buy {item.name}: {reason}")

    def _auto_buy(self) -> None:
        for category in ("weapon", "armor"):
            for item in self.catalog:
                if item.category == category and self.session.buy(self.member, item)[0]:
                    break

    def update(self, dt: float) -> None:
        ...

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        half_label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        hf = font(LAYOUT.i("shop_header_size", 22))
        surface.blit(hf.render(f"Shop -- {half_label}", True, _C["white"]), (m, 16))
        gf = font(LAYOUT.i("shop_gold_size", 18))
        loadout = self.session.loadouts[self.member]
        surface.blit(gf.render(
            f"Gold {self.session.treasury}   Slots {len(loadout.items)}/{loadout.slot_cap()}",
            True, _C["gold"]), (m, 48))
        if self.feedback:
            ff = font(LAYOUT.i("shop_hint_size", 15))
            surface.blit(ff.render(self.feedback[:46], True, _C["accent"]), (m, 78))

        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        nf = font(LAYOUT.i("shop_name_size", 20))
        sf = font(LAYOUT.i("shop_sub_size", 15))
        for i, item in enumerate(self.catalog):
            r = self._row_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            self._draw_row(surface, r, item, nf, sf)
        surface.set_clip(prev)

        if self._max_scroll() > 0:
            self.scroll_btns.draw(surface, self.scroll, self._max_scroll())
        self.done_btn.draw(surface, nf)

    def _draw_row(self, surface: pygame.Surface, r: pygame.Rect, item,
                  nf: pygame.font.Font, sf: pygame.font.Font) -> None:
        owned = self._owned(item)
        bg = _C["accent"] if owned else _C["surface"]
        pygame.draw.rect(surface, bg, r, border_radius=8)
        pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
        size = LAYOUT.i("shop_icon", 44)
        icon = load_icon(item.category)
        icon_box = pygame.Rect(r.x + 8, r.centery - size // 2, size, size)
        if icon is not None:
            surface.blit(pygame.transform.smoothscale(icon, (size, size)), icon_box)
        else:
            pygame.draw.rect(surface, _C["border"], icon_box, border_radius=6)
        tx = icon_box.right + 10
        surface.blit(nf.render(item.name[:18], True, _C["white"]), (tx, r.y + 8))
        sub = f"{item.category}  {'*' * item.stars}  {item.price}g"
        surface.blit(sf.render(sub, True, _C["text_dim"]), (tx, r.y + 36))
        tag = "OWNED -- tap to sell" if owned else "tap to buy"
        ts = sf.render(tag, True, _C["background"] if owned else _C["accent"])
        surface.blit(ts, (r.right - ts.get_width() - 10, r.y + 8))
