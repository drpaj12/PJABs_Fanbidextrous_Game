# src/ui/screens/status_screens.py
"""Watch (waiting), Reveal (window result), Half (end-of-half recap), and Final screens."""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.sim import SimMode
from src.ui.widgets import Button, MeterBar, font
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_M = CONFIG["meter"]


class WatchScreen(Screen):
    def __init__(self, app: "App", get_state: Callable[..., None]) -> None:
        super().__init__(app)
        self.get_state = get_state  # callable -> dict(team, opp, success, concede, window, clock)
        w = app.screen.get_width()
        self.success_bar = MeterBar(pygame.Rect(20, 200, w - 40, 24), _C["green"])
        self.concede_bar = MeterBar(pygame.Rect(20, 260, w - 40, 24), _C["red"])

    def handle(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        s = self.get_state()
        f = self.app.font
        surface.blit(f.render(f"Window {s['window']}   {s['clock']}", True, _C["text"]), (20, 40))
        big = font(56)
        surface.blit(big.render(f"{s['team']} - {s['opp']}", True, _C["white"]), (20, 90))
        surface.blit(f.render("Attack", True, _C["text_dim"]), (20, 176))
        self.success_bar.draw(surface, s["success"], _M["success_threshold"])
        surface.blit(f.render("Danger", True, _C["text_dim"]), (20, 236))
        self.concede_bar.draw(surface, s["concede"], _M["concede_threshold"])


class RevealScreen(Screen):
    def __init__(self, app: "App", lines: list[str],
                 on_continue: Callable[..., None]) -> None:
        super().__init__(app)
        self.lines = lines
        self.on_continue = on_continue

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        f = self.app.font
        for i, line in enumerate(self.lines):
            surface.blit(f.render(line, True, _C["text"]), (20, 60 + i * 32))
        surface.blit(f.render("tap to continue", True, _C["text_dim"]),
                     (20, surface.get_height() - 50))


class FinalScreen(Screen):
    def __init__(self, app: "App", team: int, opp: int, real_line: str | None,
                 on_continue: Optional[Callable[..., None]] = None,
                 title: str = "Full Time") -> None:
        super().__init__(app)
        self.team, self.opp, self.real_line = team, opp, real_line
        self.on_continue = on_continue
        self.title = title

    def handle(self, event: pygame.event.Event) -> None:
        if self.on_continue and event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        from src.utils.constants import LAYOUT
        from src.ui.widgets import font
        sw = surface.get_width()
        big = font(LAYOUT.i("final_title_size", 44))
        t = big.render(self.title, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, 200)))
        sc = font(LAYOUT.i("final_score_size", 40))
        s = sc.render(f"You {self.team} - {self.opp} Opp", True, _C["accent"])
        surface.blit(s, s.get_rect(center=(sw // 2, 300)))
        if self.real_line:
            rf = font(LAYOUT.i("ui_small_size", 17))
            r = rf.render(self.real_line, True, _C["text_dim"])
            surface.blit(r, r.get_rect(center=(sw // 2, 370)))


class DungeonHalfScreen(Screen):
    """End-of-half party recap: the crawl's percent-done, depth, every player's gold pot, and
    the last few crawl-log lines. A Continue button (or a tap, or the SIM 's' key) advances the
    flow into the next half's shop. Shown to leader and follower alike between halves."""

    def __init__(self, app: "App", percent: int, depth: int, total: int,
                 members: list, log_tail: list,
                 on_continue: Callable[[], None], title: str,
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.percent = percent
        self.depth = depth
        self.total = total
        self.members = list(members)            # list of (username, treasury)
        self.log_tail = list(log_tail)
        self.on_continue = on_continue
        self.title = title
        self.sim = sim
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.continue_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dhalf_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("dhalf_btn_h", 56)),
            "Continue")

    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_s):
            self.on_continue()
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        m = LAYOUT.i("screen_margin", 20)
        tf = font(LAYOUT.i("dhalf_title_size", 34))
        t = tf.render(self.title, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("dhalf_title_y", 70))))
        pf = font(LAYOUT.i("dhalf_pct_size", 52))
        p = pf.render(f"{self.percent}%", True, _C["accent"])
        surface.blit(p, p.get_rect(center=(sw // 2, LAYOUT.i("dhalf_pct_y", 150))))
        sf = font(LAYOUT.i("dhalf_sub_size", 18))
        s = sf.render(f"depth {self.depth} of {self.total}", True, _C["text_dim"])
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i("dhalf_sub_y", 200))))

        y = LAYOUT.i("dhalf_list_top", 240)
        lf = font(LAYOUT.i("dhalf_row_size", 19))
        surface.blit(lf.render("Party gold", True, _C["text_dim"]), (m, y))
        y += LAYOUT.i("dhalf_row_gap", 28)
        for username, treasury in self.members:
            surface.blit(lf.render(f"{username}", True, _C["white"]), (m, y))
            gold = lf.render(f"{treasury}g", True, _C["gold"])
            surface.blit(gold, (sw - m - gold.get_width(), y))
            y += LAYOUT.i("dhalf_row_gap", 28)

        if self.log_tail:
            y += LAYOUT.i("dhalf_section_gap", 16)
            cf = font(LAYOUT.i("dhalf_log_size", 15))
            surface.blit(cf.render("Recent", True, _C["text_dim"]), (m, y))
            y += LAYOUT.i("dhalf_log_gap", 22)
            for line in self.log_tail:
                surface.blit(cf.render(line[:46], True, _C["text"]), (m, y))
                y += LAYOUT.i("dhalf_log_gap", 22)

        self.continue_btn.draw(surface, font(LAYOUT.i("dhalf_btn_size", 19)))


class DungeonFinalScreen(Screen):
    """End of a dungeon run: the party's percent-completed score, big and centered."""

    def __init__(self, app: "App", percent: int, depth: int, total: int,
                 on_continue: Optional[Callable[..., None]] = None,
                 title: str = "Crawl Complete") -> None:
        super().__init__(app)
        self.percent = percent
        self.depth = depth
        self.total = total
        self.on_continue = on_continue
        self.title = title

    def handle(self, event: pygame.event.Event) -> None:
        if self.on_continue and event.type == pygame.MOUSEBUTTONDOWN:
            self.on_continue()

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None:
        from src.utils.constants import LAYOUT
        from src.ui.widgets import font
        sw = surface.get_width()
        tf = font(LAYOUT.i("dfinal_title_size", 40))
        t = tf.render(self.title, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, 200)))
        pf = font(LAYOUT.i("dfinal_pct_size", 56))
        p = pf.render(f"{self.percent}%", True, _C["accent"])
        surface.blit(p, p.get_rect(center=(sw // 2, 320)))
        sf = font(LAYOUT.i("dfinal_sub_size", 20))
        s = sf.render(f"dungeon completed -- depth {self.depth} of {self.total}",
                      True, _C["text_dim"])
        surface.blit(s, s.get_rect(center=(sw // 2, 400)))
        if self.on_continue:
            hf = font(LAYOUT.i("dfinal_hint_size", 16))
            h = hf.render("tap to continue", True, _C["text_dim"])
            surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 60)))
