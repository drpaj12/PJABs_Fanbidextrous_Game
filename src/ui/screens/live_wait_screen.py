# src/ui/screens/live_wait_screen.py
"""Live waiting screen: poll the relay on the wall clock until a target is reached.

Sits between play windows in a LIVE match, and also as the pre-game lobby. While it is up
it asks the relay (the PHP proxy of API-Football) for a fresh snapshot every `poll_seconds`
of wall-clock time and feeds each snapshot into the LiveFeed. It fires `on_ready` exactly
once when its target is met:

  - wait_for_lineups=True  -> the API has published a starting XI (drafting can begin)
  - target_minute is None  -> the half is over (the Extra-Time window can resolve)
  - target_minute is an int -> the live match clock has reached that minute,
                               or the half ended early (status halftime/finished)

Pre-game quota discipline (wait_for_lineups only): after one initial poll to learn the
kickoff time, the lead client does NOT poll again until kickoff is within
`live.start_minutes_before`; a countdown shows meanwhile, with a warning if the player
arrived more than `live.warn_minutes_before` early. Follower clients offset their first
poll by `feed.follower_poll_delay_seconds` so the lead's fresh write lands in the shared
cache before they read it.

All pygame lives here; all match/timing logic lives in LiveFeed/FeedClient/kickoff.
Polling is scheduled with asyncio.ensure_future so the browser/app event loop keeps
breathing.
"""
import asyncio
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.sim import SimMode
from src.ui.widgets import Button, font
from src.game.live_feed import LiveFeed
from src.game.kickoff import (seconds_to_kickoff, kickoff_phase, format_minutes,
                              PHASE_TOO_EARLY, PHASE_SOON, PHASE_ACTIVE)
from src.sync.feed_client import FeedClient
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_FINISHED_STATUS = "finished"
_COMP = CONFIG["live"]["competition_label"]
_FOLLOWER_DELAY = CONFIG["feed"]["follower_poll_delay_seconds"]
_WARN_S = CONFIG["live"]["warn_minutes_before"] * 60
_START_S = CONFIG["live"]["start_minutes_before"] * 60
_START_MIN = CONFIG["live"]["start_minutes_before"]


class LiveWaitScreen(Screen):
    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, target_minute: Optional[int],
                 on_ready: Callable[[], None], poll_seconds: float,
                 sim: Optional[SimMode] = None,
                 wait_for_lineups: bool = False,
                 wait_for_second_half: bool = False,
                 on_back: Optional[Callable[[], None]] = None) -> None:
        super().__init__(app)
        self.feed = feed
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self.target_minute = target_minute
        self.on_ready = on_ready
        self.poll_seconds = poll_seconds
        self.sim = sim
        self.wait_for_lineups = wait_for_lineups
        self.wait_for_second_half = wait_for_second_half
        self.on_back = on_back
        m = LAYOUT.i("screen_margin", 20)
        self.back_btn = Button(
            pygame.Rect(LAYOUT.i("livewait_back_x", m), LAYOUT.i("livewait_back_y", m),
                        LAYOUT.i("livewait_back_w", 96), LAYOUT.i("livewait_back_h", 44)),
            "< Back") if on_back else None
        # Lead polls immediately; followers wait out the delay so the lead writes first.
        delay = 0.0 if feed_client.is_lead else _FOLLOWER_DELAY
        self._since_poll = poll_seconds - delay
        self._polling = False
        self._did_initial_poll = False
        self._fired = False
        self._error = ""
        self._secs: Optional[int] = None
        self._phase = PHASE_ACTIVE

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
            self._did_initial_poll = True

    def _refresh_phase(self) -> None:
        self._secs = seconds_to_kickoff(self.feed.kickoff_iso(), time.time())
        self._phase = kickoff_phase(self._secs, self.feed.match_status(),
                                    _WARN_S, _START_S)

    def _should_poll(self) -> bool:
        """Between-window waits always poll. The pre-game lobby polls once (to learn the
        kickoff time), then pauses until kickoff is inside the start window."""
        if not self.wait_for_lineups:
            return True
        if not self._did_initial_poll:
            return True
        return self._phase == PHASE_ACTIVE

    def _is_ready(self) -> bool:
        status = self.feed.match_status()
        if self.wait_for_second_half:
            return (self.feed.status_short().upper() == "2H"
                    or status == _FINISHED_STATUS)
        if self.wait_for_lineups:
            return self.feed.has_lineups()
        half_over = status in (_HALFTIME_STATUS, _FINISHED_STATUS)
        if self.target_minute is None:
            return half_over
        return half_over or self.feed.current_minute() >= self.target_minute

    # -- screen -------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        # SIM only: tap to skip the wall-clock wait (no real polling on desktop dev).
        # Checked before the back button so headless smokes always advance, never loop.
        if self.sim and self.sim.enabled and event.type == pygame.MOUSEBUTTONDOWN:
            self._finish()
            return
        if (event.type == pygame.MOUSEBUTTONDOWN and self.back_btn
                and self.back_btn.hit(event.pos) and self.on_back):
            self.on_back()

    def _finish(self) -> None:
        if not self._fired:
            self._fired = True
            self.on_ready()

    def update(self, dt: float) -> None:
        if self._fired:
            return
        self._refresh_phase()
        self._since_poll += dt
        if (self._should_poll() and self._since_poll >= self.poll_seconds
                and not self._polling):
            self._since_poll = 0.0
            self._polling = True
            asyncio.ensure_future(self._poll())
        if self._is_ready():
            self._finish()

    # -- drawing ------------------------------------------------------------
    def _wait_label(self) -> str:
        if self.wait_for_second_half:
            return "Second half starts soon..."
        if self.wait_for_lineups:
            return "Waiting for team sheets..."
        if self.target_minute is None:
            return "Playing to half time..."
        return f"Playing to minute {self.target_minute}'..."

    def _draw_centered(self, surface: pygame.Surface, text: str, size_key: str,
                       size_def: int, y_key: str, y_def: int, color) -> None:
        sw = surface.get_width()
        f = font(LAYOUT.i(size_key, size_def))
        s = f.render(text, True, color)
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i(y_key, y_def))))

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        if self.back_btn:
            self.back_btn.draw(surface, font(LAYOUT.i("livewait_back_size", 20)))
        self._draw_centered(surface, f"LIVE  -  {_COMP}", "livewait_header_size", 22,
                            "livewait_header_y", 150, _C["accent"])

        teams = f"{self.feed.home_team()} v {self.feed.away_team()}".strip(" v")
        if teams:
            self._draw_centered(surface, teams, "livewait_teams_size", 26,
                                "livewait_teams_y", 210, _C["white"])

        countdown = (self.wait_for_lineups and self._phase != PHASE_ACTIVE
                     and self._secs is not None)
        if countdown:
            self._draw_pregame(surface)
        else:
            self._draw_active(surface)

    def _draw_pregame(self, surface: pygame.Surface) -> None:
        """Pre-game lobby, kickoff still far enough off that we are not polling yet."""
        self._draw_centered(surface, f"Kickoff in {format_minutes(self._secs)}",
                            "livewait_clock_size", 48, "livewait_clock_y", 320,
                            _C["red"])
        if self._phase == PHASE_TOO_EARLY:
            warn = "Too early -- live data is not available yet."
            sub = "Team sheets post about an hour before kickoff."
            self._draw_centered(surface, warn, "livewait_wait_size", 22,
                                "livewait_wait_y", 410, _C["red"])
            self._draw_centered(surface, sub, "ui_small_size", 17,
                                "livewait_msg_y", 470, _C["text_dim"])
        else:  # PHASE_SOON
            sub = f"Live polling starts {_START_MIN} min before kickoff."
            self._draw_centered(surface, "Almost there...", "livewait_wait_size", 22,
                                "livewait_wait_y", 410, _C["text_dim"])
            self._draw_centered(surface, sub, "ui_small_size", 17,
                                "livewait_msg_y", 470, _C["text_dim"])

    def _draw_active(self, surface: pygame.Surface) -> None:
        """Polling: show the live match clock/status and the current wait target."""
        clock = f"{self.feed.current_minute()}'   {self.feed.match_status()}"
        self._draw_centered(surface, clock, "livewait_clock_size", 48,
                            "livewait_clock_y", 320, _C["white"])
        self._draw_centered(surface, self._wait_label(), "livewait_wait_size", 22,
                            "livewait_wait_y", 410, _C["text_dim"])
        msg = self._error or "refreshing on the match clock"
        self._draw_centered(surface, msg, "ui_small_size", 17,
                            "livewait_msg_y", 470, _C["text_dim"])
