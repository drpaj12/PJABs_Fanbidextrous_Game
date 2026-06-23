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
from src.ui.widgets import (Button, LogList, ScrollButtons, draw_depth_meter,
                            draw_match_banner, font, wall_clock_str, wrap_text)
from src.ui.sim import SimMode
from src.sync.party_coordinator import PartyCoordinator
from src.game.dungeon import gate_step, monster_flavor
from src.game.items import build_catalog
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
                 can_resolve: Optional[Callable[[int], bool]] = None,
                 pick_history: Optional[dict] = None,
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.coord = coord
        self.window = window
        self.label = label
        self.on_continue = on_continue
        self.require_all = require_all
        self.on_poll = on_poll
        # Per-stat lock state for the predict dials (mirrors live_play_screen): green = locked
        # (the bet), orange = adjusted but not locked, red = untouched.
        self.locked: set = set()
        self.touched: set = set()
        # Crawl-long record of THIS player's submitted picks per window, owned by the flow so it
        # survives the per-window screen rebuilds; the wait-phase "Picks in" panel reads it.
        self.pick_history = pick_history if pick_history is not None else {}
        # LIVE data gate: the leader resolves this window only when can_resolve(window) is True
        # (the live feed actually covers the window's end minute), so the actuals query reads
        # real per-window deltas instead of stale zeros. None in SIM -> resolve as soon as the
        # require_all picks gate allows (the recorded feed always holds the data).
        self.can_resolve = can_resolve
        self.sim = sim
        self.phase = "edit"
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        # Held potions the player can deploy THIS window. use_potions = item_ids toggled ON;
        # potion_zoom = item_id of the zoom-in card currently open (None = no overlay).
        self.use_potions: set = set()
        self.potion_zoom: Optional[str] = None
        self._potions = self._held_potions()
        self._polling = False
        self._elapsed = _POLL
        self._logged = 0
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.action_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dp_btn_h", 56) - 12, sw - 2 * m,
                        LAYOUT.i("dp_btn_h", 56)), "Submit picks")
        # Crawl log UNDERNEATH the resolution summary, scrollable via the ScrollButtons gutter
        # (mirrors DungeonPlayScreen -- no mouse wheel on a phone).
        log_top = LAYOUT.i("dp_log_top", 372)
        log_full = pygame.Rect(m, log_top, sw - 2 * m,
                               self.action_btn.rect.top - 12 - log_top)
        self.log = LogList(pygame.Rect(log_full.x, log_full.y,
                                       log_full.width - ScrollButtons.gutter(),
                                       log_full.height))
        self.log_scroll = ScrollButtons(log_full)

    def _stat_step(self) -> int:
        return LAYOUT.i("dp_stat_row_h", 48) + LAYOUT.i("dp_stat_gap", 6)

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("dp_content_top", 92)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * self._stat_step(), w, LAYOUT.i("dp_stat_row_h", 48))

    def _held_potions(self) -> list:
        """This player's held consumables (built from the shared lineup pool + their own item
        ids). Each may be deployed for the current window via the USE toggle."""
        me = self.coord.me()
        if me is None:
            return []
        held = list(me.items)
        catalog = {it.item_id: it for it in build_catalog(self.coord.pool, self.coord.half())}
        return [catalog[i] for i in held if i in catalog and catalog[i].category == "consumable"]

    def _potion_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("pplay_potion_top", 470)
        step = LAYOUT.i("pplay_potion_row_h", 40) + LAYOUT.i("pplay_potion_row_gap", 6)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * step, w, LAYOUT.i("pplay_potion_row_h", 40))

    def _potion_at(self, pos: tuple) -> Optional[str]:
        for i, it in enumerate(self._potions):
            if self._potion_rect(i).collidepoint(pos):
                return it.item_id
        return None

    def _zoom_box(self) -> pygame.Rect:
        w, h = LAYOUT.i("pplay_zoom_w", 300), LAYOUT.i("pplay_zoom_h", 220)
        sw, sh = self.app.screen.get_size()
        return pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)

    def _zoom_btn_rect(self) -> pygame.Rect:
        box, pad = self._zoom_box(), LAYOUT.i("pplay_zoom_pad", 18)
        bh = LAYOUT.i("pplay_zoom_btn_h", 52)
        return pygame.Rect(box.x + pad, box.bottom - pad - bh, box.width - 2 * pad, bh)

    def handle(self, event: pygame.event.Event) -> None:
        if self.phase == "edit":
            if self.sim and self.sim.is_key(event, pygame.K_f):
                self._submit()
                return
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
            # Potion zoom overlay intercepts all taps: USE toggles deployment, anything closes.
            if self.potion_zoom is not None:
                if self._zoom_btn_rect().collidepoint(event.pos):
                    self._toggle_potion(self.potion_zoom)
                self.potion_zoom = None
                return
            if self.action_btn.hit(event.pos):
                self._submit()
                return
            pid = self._potion_at(event.pos)
            if pid is not None:
                self.potion_zoom = pid
                return
            for i, s in enumerate(_STATS):
                r = self._stat_rect(i)
                if r.collidepoint(event.pos):
                    self._tap_stat(s["code"], event.pos[0], r)
                    return
        elif self.phase == "resolved":
            self.log.handle(event)
            if event.type == pygame.MOUSEBUTTONDOWN and self.log_scroll.contains(event.pos):
                self.log.scroll_to(self.log_scroll.handle(
                    event, self.log.scroll, self.log.max_scroll()))
                return
            if event.type == pygame.MOUSEBUTTONDOWN and self.action_btn.hit(event.pos):
                self.on_continue()
            elif self.sim and self.sim.is_key(event, pygame.K_s):
                self.on_continue()

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:           # "+" stepper -> adjust (orange)
            self.lines[code] += 1
            self._arm(code)
        elif x > r.right - 112:        # "-" stepper -> adjust (orange)
            self.lines[code] = max(0, self.lines[code] - 1)
            self._arm(code)
        else:                          # row body -> toggle the lock (green = the bet)
            if code in self.locked:
                self.locked.discard(code)
            else:
                self.locked.add(code)
                self.touched.discard(code)

    def _arm(self, code: str) -> None:
        """A stepper tap adjusts the line, marking the stat orange (touched, not yet locked)."""
        self.touched.add(code)
        self.locked.discard(code)

    def _toggle_potion(self, item_id: str) -> None:
        """Toggle whether this held potion is deployed for the current window."""
        if item_id in self.use_potions:
            self.use_potions.discard(item_id)
        else:
            self.use_potions.add(item_id)

    def _submit(self) -> None:
        # Record this window's picks for the "Picks in" panel before sending them upstream.
        self.pick_history[self.window] = dict(self.lines)
        asyncio.ensure_future(self.coord.submit_pick(self.window, dict(self.lines),
                                                     use=sorted(self.use_potions)))
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
                # on_poll may have just recorded a fresh snapshot; gate resolution on the feed
                # covering this window before the leader scores it (LIVE only -- see can_resolve).
                if (self.coord.is_leader
                        and (self.can_resolve is None or self.can_resolve(self.window))):
                    await self.coord.leader_try_resolve(self.window, self.require_all)
            finally:
                self._polling = False
        asyncio.ensure_future(go())

    def _enter_resolved(self) -> None:
        self.phase = "resolved"
        # Encounter flavor first (display-only, wrapped to the log width), then the
        # leader-pushed resolution log -- so the scrollable log reads as encounter + outcome.
        if self._logged == 0:
            v = self.coord.view()
            size = max(1, len(v.get("members", [])))
            flavor = monster_flavor(self.coord.half(), size, int(v.get("threat", 0)))["text"]
            ff = font(LAYOUT.i("play_log_line_size", 16))
            for wline in wrap_text(flavor, ff, self.log.rect.width - 8):
                self.log.add(wline)
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
            self._draw_potions(surface)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))
            if self.potion_zoom is not None:
                self._draw_potion_zoom(surface)
        elif self.phase == "wait":
            self._draw_picks_panel(surface)
        else:
            self._draw_resolved(surface, v)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))

    def _draw_dials(self, surface: pygame.Surface) -> None:
        sf = font(LAYOUT.i("dp_stat_size", 19))
        cr = LAYOUT.i("pplay_lock_circle_r", 9)
        for i, s in enumerate(_STATS):
            code = s["code"]
            r = self._stat_rect(i)
            locked = code in self.locked
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            # Accent border when locked; tri-color dot: green locked / orange touched / red new.
            pygame.draw.rect(surface, _C["accent"] if locked else _C["border"], r,
                             width=2, border_radius=8)
            dot = (_C["green"] if locked
                   else _C["orange"] if code in self.touched else _C["red"])
            pygame.draw.circle(surface, dot, (r.x + 18, r.centery), cr)
            surface.blit(sf.render(f"{s['label']}: {self.lines[code]}", True, _C["white"]),
                         (r.x + 38, r.y + 12))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 10))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 10))

    def _draw_picks_panel(self, surface: pygame.Surface) -> None:
        """Wait phase: 'Picks in' + a Windows panel listing each window's submitted picks,
        newest-first, with the window currently being resolved drawn white + underlined. A
        gated status line under the panel says what we are waiting on (mirrors the previous
        game's locked-windows panel)."""
        m = LAYOUT.i("screen_margin", 20)
        pad = LAYOUT.i("pplay_panel_pad", 14)
        gap = LAYOUT.i("pplay_panel_line_gap", 26)
        top = LAYOUT.i("dp_content_top", 92)
        tf = font(LAYOUT.i("pplay_panel_title_size", 20))
        lf = font(LAYOUT.i("pplay_panel_line_size", 17))
        order = [s["code"] for s in _STATS]
        rows = 1 + len(self.pick_history)              # title + one row per submitted window
        box = pygame.Rect(m, top, surface.get_width() - 2 * m, pad * 2 + (rows + 1) * gap)
        pygame.draw.rect(surface, _C["surface"], box, border_radius=8)
        pygame.draw.rect(surface, _C["border"], box, width=2, border_radius=8)
        x, y = box.x + pad, box.y + pad
        surface.blit(tf.render("Picks in", True, _C["accent"]), (x, y))
        for w in sorted(self.pick_history, reverse=True):
            y += gap
            lines = self.pick_history[w]
            picks = "  ".join(f"{c[:3].upper()} {lines[c]}" for c in order if c in lines)
            resolving = (w == self.window)
            img = lf.render(f"W{w}: {picks}", True,
                            _C["white"] if resolving else _C["text_dim"])
            surface.blit(img, (x, y))
            if resolving:
                uy = y + img.get_height() + 1
                pygame.draw.line(surface, _C["white"], (x, uy),
                                 (x + img.get_width(), uy), 1)
        # Gated status under the windows list.
        if self.can_resolve is not None and not self.can_resolve(self.window):
            msg = "Waiting for the match..."
        elif self.coord.is_leader:
            msg = "Resolving..."
        else:
            msg = "Waiting for the party..."
        surface.blit(lf.render(msg, True, _C["accent"]), (x, y + gap))

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

    def _draw_potions(self, surface: pygame.Surface) -> None:
        """Held-potion chips (tap to zoom). A deployed potion is tinted green with 'USED';
        a held-but-idle one stays neutral. Nothing drawn when the player holds no potions."""
        if not self._potions:
            return
        m = LAYOUT.i("screen_margin", 20)
        lf = font(LAYOUT.i("pplay_potion_label_size", 16))
        surface.blit(lf.render("Potions (tap to deploy this window)", True, _C["text_dim"]),
                     (m, LAYOUT.i("pplay_potion_top", 470) - lf.get_height() - 4))
        pf = font(LAYOUT.i("pplay_potion_size", 17))
        for i, it in enumerate(self._potions):
            r = self._potion_rect(i)
            on = it.item_id in self.use_potions
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["green"] if on else _C["border"], r,
                             width=2, border_radius=8)
            val = it.effect.get("value", 0)
            surface.blit(pf.render(f"{it.name}  (+{val})", True, _C["white"]),
                         (r.x + 12, r.centery - pf.get_height() // 2))
            tag = "USED" if on else "TAP"
            timg = pf.render(tag, True, _C["green"] if on else _C["text_dim"])
            surface.blit(timg, (r.right - timg.get_width() - 12,
                                r.centery - timg.get_height() // 2))

    def _draw_potion_zoom(self, surface: pygame.Surface) -> None:
        """Zoom-in item card with a USE toggle (mirrors the draft player-detail overlay)."""
        it = next((p for p in self._potions if p.item_id == self.potion_zoom), None)
        if it is None:
            return
        box = self._zoom_box()
        pad = LAYOUT.i("pplay_zoom_pad", 18)
        pygame.draw.rect(surface, _C["surface"], box, border_radius=10)
        pygame.draw.rect(surface, _C["accent"], box, width=2, border_radius=10)
        tf = font(LAYOUT.i("pplay_zoom_title_size", 22))
        bf = font(LAYOUT.i("pplay_zoom_body_size", 17))
        x, y = box.x + pad, box.y + pad
        surface.blit(tf.render(it.name, True, _C["white"]), (x, y))
        y += tf.get_height() + 8
        val = it.effect.get("value", 0)
        for line in wrap_text(f"Deploy for +{val} on this window's gate roll. Consumed on use.",
                              bf, box.width - 2 * pad):
            surface.blit(bf.render(line, True, _C["text_dim"]), (x, y))
            y += bf.get_height() + 2
        on = it.item_id in self.use_potions
        btn = Button(self._zoom_btn_rect(), "Cancel deploy" if on else "USE this window")
        btn.draw(surface, bf)

    def _draw_resolved(self, surface: pygame.Surface, v: dict) -> None:
        # Resolution summary first (cells -> depth meter -> per-prediction strip), top-down,
        # with the scrollable crawl log UNDERNEATH it.
        m = LAYOUT.i("screen_margin", 20)
        cells_y = LAYOUT.i("dp_content_top", 92)
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
        self.log.draw(surface)
        if self.log.max_scroll() > 0:
            self.log_scroll.draw(surface, self.log.scroll, self.log.max_scroll())

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
