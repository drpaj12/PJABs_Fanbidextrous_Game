# src/ui/screens/live_wait_screen.py
"""Live waiting screen: poll the relay on the wall clock until a target is reached.

Sits between play windows in a LIVE match. While it is up, it asks the relay (the PHP
proxy of API-Football) for a fresh snapshot every `poll_seconds` of wall-clock time and
feeds each snapshot into the LiveFeed. It fires `on_ready` exactly once when its target
is met:

  - wait_for_lineups=True  -> the API has published a starting XI (drafting can begin)
  - target_minute is None  -> the half is over (the Extra-Time window can resolve)
  - target_minute is an int -> the live match clock has reached that minute,
                               or the half ended early (status halftime/finished)

All pygame lives here; all match logic lives in LiveFeed/FeedClient. Polling is scheduled
with asyncio.ensure_future so the browser/app event loop keeps breathing.
"""
import asyncio
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.sim import SimMode
from src.ui.widgets import font
from src.game.live_feed import LiveFeed
from src.sync.feed_client import FeedClient
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_FINISHED_STATUS = "finished"
_COMP = CONFIG["live"]["competition_label"]


class LiveWaitScreen(Screen):
    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, target_minute: Optional[int],
                 on_ready: Callable[[], None], poll_seconds: float,
                 sim: Optional[SimMode] = None,
                 wait_for_lineups: bool = False) -> None:
        super().__init__(app)
        self.feed = feed
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self.target_minute = target_minute
        self.on_ready = on_ready
        self.poll_seconds = poll_seconds
        self.sim = sim
        self.wait_for_lineups = wait_for_lineups
        self._since_poll = poll_seconds   # poll immediately on entry
        self._polling = False
        self._fired = False
        self._error = ""

    # -- polling ------------------------------------------------------------
    async def _poll(self) -> None:
        try:
            snapshot = await self.feed_client.get_feed(self.fixture_id)
            self.feed.record(snapshot)
            self._error = ""
        except Exception as exc:                       # network/parse: keep retrying
            self._error = f"reconnecting ({type(exc).__name__})"
        finally:
            self._polling = False

    def _is_ready(self) -> bool:
        status = self.feed.match_status()
        if self.wait_for_lineups:
            return self.feed.has_lineups()
        half_over = status in (_HALFTIME_STATUS, _FINISHED_STATUS)
        if self.target_minute is None:
            return half_over
        return half_over or self.feed.current_minute() >= self.target_minute

    # -- screen -------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        # SIM only: tap to skip the wall-clock wait (no real polling on desktop dev).
        if self.sim and self.sim.enabled and event.type == pygame.MOUSEBUTTONDOWN:
            self._finish()

    def _finish(self) -> None:
        if not self._fired:
            self._fired = True
            self.on_ready()

    def update(self, dt: float) -> None:
        if self._fired:
            return
        self._since_poll += dt
        if self._since_poll >= self.poll_seconds and not self._polling:
            self._since_poll = 0.0
            self._polling = True
            asyncio.ensure_future(self._poll())
        if self._is_ready():
            self._finish()

    def _wait_label(self) -> str:
        if self.wait_for_lineups:
            return "Waiting for team sheets..."
        if self.target_minute is None:
            return "Playing to half time..."
        return f"Playing to minute {self.target_minute}'..."

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        hf = font(LAYOUT.i("livewait_header_size", 22))
        h = hf.render(f"LIVE  -  {_COMP}", True, _C["accent"])
        surface.blit(h, h.get_rect(center=(sw // 2, LAYOUT.i("livewait_header_y", 150))))

        teams = f"{self.feed.home_team()} v {self.feed.away_team()}".strip(" v")
        if teams:
            tf = font(LAYOUT.i("livewait_teams_size", 26))
            t = tf.render(teams, True, _C["white"])
            surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("livewait_teams_y", 210))))

        clock = f"{self.feed.current_minute()}'   {self.feed.match_status()}"
        cf = font(LAYOUT.i("livewait_clock_size", 48))
        c = cf.render(clock, True, _C["white"])
        surface.blit(c, c.get_rect(center=(sw // 2, LAYOUT.i("livewait_clock_y", 320))))

        wf = font(LAYOUT.i("livewait_wait_size", 22))
        w = wf.render(self._wait_label(), True, _C["text_dim"])
        surface.blit(w, w.get_rect(center=(sw // 2, LAYOUT.i("livewait_wait_y", 410))))

        msg = self._error or "refreshing on the match clock"
        mf = font(LAYOUT.i("ui_small_size", 17))
        m = mf.render(msg, True, _C["text_dim"])
        surface.blit(m, m.get_rect(center=(sw // 2, LAYOUT.i("livewait_msg_y", 470))))
