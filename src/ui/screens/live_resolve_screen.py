# src/ui/screens/live_resolve_screen.py
"""Resolve a picked schedule game to its real API-Football fixture id, live.

Sits in front of the live flow. While up, it polls the relay's live-fixtures endpoint
(live_fixtures.php, a filtered proxy of fixtures?live=all) every `poll_seconds` and asks
live_resolver to match the picked game's teams to a match that is in play right now. The
moment a match is found it fires `on_resolved(real_id)` exactly once and the existing live
flow takes over with the real id.

A World Cup match only appears in fixtures?live=all once it is IN PLAY, so before kickoff
this screen shows the kickoff countdown and keeps looking -- which is exactly the intended
"resolve the game as it is played" behavior. All pygame lives here; the matching itself is
the pure src/game/live_resolver.

Polling is fire-and-forget via asyncio.ensure_future so the browser/app event loop keeps
breathing. Only the lead client spends upstream quota (FeedClient gates that).
"""
import asyncio
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.sim import SimMode
from src.ui.widgets import Button, font
from src.game.live_resolver import resolve_fixture_id
from src.game.kickoff import seconds_to_kickoff, format_minutes
from src.sync.feed_client import FeedClient
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_COMP = CONFIG["live"]["competition_label"]
_FOLLOWER_DELAY = CONFIG["feed"]["follower_poll_delay_seconds"]


class LiveResolveScreen(Screen):
    def __init__(self, app: "App", feed_client: FeedClient, home: str, away: str,
                 kickoff_iso: str, on_resolved: Callable[[int], None],
                 poll_seconds: float, fallback_id: int,
                 sim: Optional[SimMode] = None,
                 on_back: Optional[Callable[[], None]] = None) -> None:
        super().__init__(app)
        self.feed_client = feed_client
        self.home = home
        self.away = away
        self.kickoff_iso = kickoff_iso
        self.on_resolved = on_resolved
        self.poll_seconds = poll_seconds
        self.fallback_id = fallback_id
        self.sim = sim
        self.on_back = on_back
        m = LAYOUT.i("screen_margin", 20)
        self.back_btn = Button(
            pygame.Rect(LAYOUT.i("livewait_back_x", m), LAYOUT.i("livewait_back_y", m),
                        LAYOUT.i("livewait_back_w", 96), LAYOUT.i("livewait_back_h", 44)),
            "< Back") if on_back else None
        delay = 0.0 if feed_client.is_lead else _FOLLOWER_DELAY
        self._since_poll = poll_seconds - delay   # lead polls immediately
        self._polling = False
        self._fired = False
        self._error = ""
        self._fixtures: list[dict] = []
        self._secs: Optional[int] = None

    # -- polling ------------------------------------------------------------
    async def _poll(self) -> None:
        try:
            payload = await self.feed_client.get_live_fixtures()
            self._fixtures = payload.get("response") or []
            self._error = ""
        except Exception as exc:                       # network/parse: keep retrying
            self._error = f"reconnecting ({type(exc).__name__})"
        finally:
            self._polling = False

    def _resolved_id(self) -> Optional[int]:
        return resolve_fixture_id(self.home, self.away, self._fixtures)

    # -- screen -------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        # SIM only: tap to skip the live lookup (no real polling on desktop dev/headless).
        if self.sim and self.sim.enabled and event.type == pygame.MOUSEBUTTONDOWN:
            self._finish(self.fallback_id)
            return
        if (event.type == pygame.MOUSEBUTTONDOWN and self.back_btn
                and self.back_btn.hit(event.pos) and self.on_back):
            self.on_back()

    def _finish(self, real_id: int) -> None:
        if not self._fired:
            self._fired = True
            self.on_resolved(real_id)

    def update(self, dt: float) -> None:
        if self._fired:
            return
        self._secs = seconds_to_kickoff(self.kickoff_iso, time.time())
        self._since_poll += dt
        if self._since_poll >= self.poll_seconds and not self._polling:
            self._since_poll = 0.0
            self._polling = True
            asyncio.ensure_future(self._poll())
        rid = self._resolved_id()
        if rid is not None:
            self._finish(rid)

    # -- drawing ------------------------------------------------------------
    def _draw_centered(self, surface: pygame.Surface, text: str, size_key: str,
                       size_def: int, y_key: str, y_def: int, color) -> None:
        sw = surface.get_width()
        f = font(LAYOUT.i(size_key, size_def))
        s = f.render(text, True, color)
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i(y_key, y_def))))

    def draw(self, surface: pygame.Surface) -> None:
        if self.back_btn:
            self.back_btn.draw(surface, font(LAYOUT.i("livewait_back_size", 20)))
        self._draw_centered(surface, f"LIVE  -  {_COMP}", "livewait_header_size", 22,
                            "livewait_header_y", 150, _C["accent"])
        teams = f"{self.home} v {self.away}".strip(" v")
        if teams:
            self._draw_centered(surface, teams, "livewait_teams_size", 26,
                                "livewait_teams_y", 210, _C["white"])

        if self._secs is not None and self._secs > 0:
            self._draw_centered(surface, f"Kickoff in {format_minutes(self._secs)}",
                                "livewait_clock_size", 48, "livewait_clock_y", 320,
                                _C["red"])
            label = "Finding the live match feed..."
        else:
            self._draw_centered(surface, "Connecting to live match...",
                                "livewait_clock_size", 30, "livewait_clock_y", 320,
                                _C["white"])
            label = "Matching the live feed by team..."
        self._draw_centered(surface, label, "livewait_wait_size", 22,
                            "livewait_wait_y", 410, _C["text_dim"])
        msg = self._error or "Live data appears once the match is in play."
        self._draw_centered(surface, msg, "ui_small_size", 17,
                            "livewait_msg_y", 470, _C["text_dim"])
