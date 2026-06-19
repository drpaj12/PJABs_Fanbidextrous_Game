# src/ui/screens/status_screens.py
"""Watch (waiting), Reveal (window result), and Final (full-time) screens."""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import MeterBar
from src.utils.constants import CONFIG

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
        big = pygame.font.SysFont("arial", 56)
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
