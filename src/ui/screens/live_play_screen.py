# src/ui/screens/live_play_screen.py
"""LivePlayScreen: the unified, always-running live half screen.

One screen for the whole half. It runs a wall-clock match clock (MatchClock), shows the
five stat dials + steppers and the active-player picker (ported from PlayScreen), and
locks/resolves windows automatically as the live match clock crosses 5-minute boundaries
-- no separate "wait" screen between windows.

Lifecycle within a single half:
  * Pre-kickoff (lobby): the kickoff countdown is shown (ported from LiveWaitScreen) and
    the player may pre-set window 1 on the same editor. No API polling yet (quota
    discipline -- mirrors LiveWaitScreen's start gate).
  * Active: every `poll_seconds` of wall-clock time a relay snapshot is fetched and fed
    into the LiveFeed. As each window boundary passes, the current dial snapshot is locked
    for that window and the PREVIOUS window is resolved via the on_lock bridge; the
    returned WindowReport is shown inline.
  * Half over (feed reports halftime): the Extra-Time window is resolved if owned and
    on_finished() is called so the flow can show the FinalScreen.

The screen NEVER touches the scoring engine: on_lock(window, preds, active_id, use_power)
is the bridge -- the flow resolves and returns the WindowReport that we render.

All timing reads go through the injected now_fn so the logic is testable; all pygame and
all layout numbers (liveplay_* in layout_config.json) live in this file/config.
"""
import asyncio
import time
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, PlayerDetail, ScrollButtons, athlete_card, font
from src.ui.sim import SimMode
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.game.live_feed import LiveFeed
from src.game.match_clock import MatchClock
from src.game.half_clock import HalfClock
from src.game.window_report import WindowReport
from src.game.kickoff import (seconds_to_kickoff, kickoff_phase, format_minutes,
                              PHASE_ACTIVE)
from src.sync.feed_client import FeedClient
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_FINISHED_STATUS = "finished"
_LIVE_STATUS = "live"
_FOLLOWER_DELAY = CONFIG["feed"]["follower_poll_delay_seconds"]
_WARN_S = CONFIG["live"]["warn_minutes_before"] * 60
_START_S = CONFIG["live"]["start_minutes_before"] * 60
_START_MIN = CONFIG["live"]["start_minutes_before"]


def lock_and_resolve_plan(entered: list[int],
                          editing_start: int) -> list[tuple[int, Optional[int]]]:
    """For each newly entered window w: (lock=w, resolve=w-1 or None when w-1<editing_start)."""
    out = []
    for w in entered:
        resolve = w - 1 if (w - 1) >= editing_start else None
        out.append((w, resolve))
    return out


def windows_ready(pending: set[int], last_known_minute: int,
                  clock: HalfClock) -> list[int]:
    """Of the windows queued for resolution, those whose end minute the feed now covers.

    A window must NOT resolve until the feed holds a snapshot at or past its end minute --
    otherwise a window slept through (tab backgrounded) or stalled during a lead outage
    would score against stale cumulative totals (every stat reads delta 0, and the whole
    catch-up jump later dumps onto one window). Gating on data availability keeps the totals
    credited even when per-window granularity across a long gap cannot be reconstructed."""
    return sorted(w for w in pending if last_known_minute >= clock.window_end(w))


def windows_to_enter(max_entered: int, playing_window: int) -> list[int]:
    """Window indices to lock this frame, using a monotonic high-water mark instead of a
    frame delta. Forward progress (incl. catch-up after a backgrounded tab) returns the new
    indices; a backward clock correction from re-alignment returns [] so an already-played
    window is never re-locked."""
    return list(range(max_entered + 1, playing_window + 1))


class LivePlayScreen(Screen):
    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 match_clock: MatchClock, fixture_id: int,
                 editing_window_start: int,
                 on_lock: Callable[[int, list[Prediction], str, bool], WindowReport],
                 on_finished: Callable[[], None], poll_seconds: float,
                 available: list[DraftedAthlete],
                 half_label: str = "",
                 resync_threshold_seconds: float = 30.0,
                 now_fn: Callable[[], float] = time.time,
                 sim: Optional[SimMode] = None,
                 on_snapshot: Optional[Callable[[dict], None]] = None) -> None:
        super().__init__(app)
        self.feed = feed
        self.feed_client = feed_client
        self.mc = match_clock
        self.fixture_id = fixture_id
        self.editing_start = editing_window_start
        self.on_lock = on_lock
        self.on_finished = on_finished
        self.poll_seconds = poll_seconds
        self.available = available
        self.half_label = half_label
        self._resync_threshold = resync_threshold_seconds
        self.now_fn = now_fn
        self.sim = sim
        self.on_snapshot = on_snapshot

        # -- editor state (the window the player is currently filling in) --
        self.edit_window = editing_window_start
        self.lines: dict[str, int] = {s["code"]: s["default_line"] for s in _STATS}
        self.locked: set[str] = set()    # green: committed dials for this edit window
        self.touched: set[str] = set()   # orange: adjusted but not locked
        self.active_id: Optional[str] = None
        self.use_power = False
        self.feedback = ""
        self.scroll = 0
        self.zoom_idx: Optional[int] = None  # tapped player's detail panel, or None

        # -- locked windows (snapshots) + the latest resolved report (inline reveal) --
        # window -> (preds, active_id, use_power)
        self._locked: dict[int, tuple[list[Prediction], Optional[str], bool]] = {}
        self.last_report: Optional[WindowReport] = None
        # Windows locked at a boundary but waiting for the feed to cover their end minute
        # before they resolve (focus-loss / lead-outage safety -- see windows_ready()).
        self._pending_resolve: set[int] = set()

        # -- wall-clock + polling --
        now = self.now_fn()
        # High-water mark of the highest playing window entered so far (re-align safe).
        self._max_entered = editing_window_start - 1
        # Lead polls on the first eligible frame; followers offset so the lead writes first.
        delay = 0.0 if feed_client.is_lead else _FOLLOWER_DELAY
        self._last_poll_epoch = now - poll_seconds + delay
        self._polling = False
        self._did_initial_poll = False
        self._finished = False
        self._error = ""
        self._poll_count = 0
        self._secs: Optional[int] = None
        self._phase = PHASE_ACTIVE

        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        bh = LAYOUT.i("liveplay_update_btn_h", 56)
        bw = LAYOUT.i("liveplay_update_btn_w", 150)
        self.update_btn = Button(
            pygame.Rect(sw - m - bw, sh - bh - 12, bw, bh), "Update now")
        self.scroll_btns = ScrollButtons(self._viewport())
        self.detail = PlayerDetail(pygame.Rect(m, 120, sw - 2 * m, sh - 240))

    # -- phase / polling ----------------------------------------------------
    def _refresh_phase(self) -> None:
        self._secs = seconds_to_kickoff(self.feed.kickoff_iso(), self.now_fn())
        self._phase = kickoff_phase(self._secs, self.feed.match_status(),
                                    _WARN_S, _START_S)

    def _should_poll(self) -> bool:
        """Poll once initially to learn the kickoff time, then only while active (within the
        start gate or under way). Pre-kickoff lobby does not poll -- quota discipline."""
        if not self._did_initial_poll:
            return True
        return self._phase == PHASE_ACTIVE

    async def _poll(self) -> None:
        self._poll_count += 1
        try:
            snapshot = await self.feed_client.get_feed(self.fixture_id)
            self.feed.record(snapshot)
            if self.on_snapshot is not None:
                self.on_snapshot(snapshot)
            self._error = ""
        except Exception as exc:                       # network/parse: keep retrying
            self._error = f"reconnecting ({type(exc).__name__})"
        finally:
            self._polling = False
            self._did_initial_poll = True

    def _kick_poll(self, now: float) -> None:
        if not self._polling:
            self._polling = True
            self._last_poll_epoch = now
            asyncio.ensure_future(self._poll())

    # -- editor -> predictions ---------------------------------------------
    def _current_preds(self) -> list[Prediction]:
        return [Prediction(s["code"], self.lines[s["code"]])
                for s in _STATS if s["code"] in self.locked]

    def _reset_editor(self) -> None:
        """Move to the next edit window: reset dials to defaults, keep the chosen player."""
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self.locked.clear()
        self.touched.clear()
        self.feedback = ""
        self.scroll = 0

    def _lock_window(self, window: int) -> None:
        self._locked[window] = (self._current_preds(), self.active_id, self.use_power)

    def _resolve_window(self, window: int) -> None:
        preds, active_id, use_power = self._locked[window]
        if not active_id:
            return  # no player chosen for that window -> nothing to score
        self.last_report = self.on_lock(window, preds, active_id, use_power)

    # -- per-frame logic ----------------------------------------------------
    def update(self, dt: float) -> None:
        if self._finished:
            return
        now = self.now_fn()
        self._refresh_phase()

        # Wall-clock poll, gated like LiveWaitScreen (no pre-kickoff polling).
        if (self._should_poll() and not self._polling
                and now - self._last_poll_epoch >= self.poll_seconds):
            self._kick_poll(now)

        # Re-align the wall clock to the API minute when our estimate has drifted; the
        # second-half anchor starts as an estimate and the first-half anchor can lag too.
        if self.feed.match_status() == _LIVE_STATUS and self.feed.current_minute() > 0:
            api_in_half = max(0, self.feed.current_minute() - self.mc.clock.start_minute)
            self.mc = self.mc.realign(api_in_half, now, self._resync_threshold)

        # Lock each newly-entered window (high-water mark) and queue the one before it.
        cur = self.mc.playing_window(now)
        for lock_w, resolve_w in lock_and_resolve_plan(
                windows_to_enter(self._max_entered, cur), self.editing_start):
            self._lock_window(lock_w)
            if (resolve_w is not None and resolve_w in self._locked
                    and self._locked[resolve_w][1]):
                self._pending_resolve.add(resolve_w)
            self.edit_window = lock_w + 1
            self._reset_editor()
        self._max_entered = max(self._max_entered, cur)

        # Resolve queued windows only once the feed actually covers their end minute, so a
        # window slept through (or stalled during a lead outage) scores against real totals
        # instead of stale zeros. The catch-up poll lands a frame or two after we wake.
        self._drain_pending()

        # Half over: resolve the final (ET) window if owned, then hand off to the flow.
        if self.feed.match_status() in (_HALFTIME_STATUS, _FINISHED_STATUS):
            self._handle_halftime()

    def _drain_pending(self) -> None:
        for w in windows_ready(self._pending_resolve, self.feed.last_known_minute(),
                               self.mc.clock):
            self._resolve_window(w)
            self._pending_resolve.discard(w)

    def _handle_halftime(self) -> None:
        # Match over: force-resolve anything still waiting on data (best effort with whatever
        # totals we have), then the ET window if owned.
        for w in sorted(self._pending_resolve):
            self._resolve_window(w)
        self._pending_resolve.clear()
        et = self.mc.clock.extra_time_window
        if et in self._locked and self._locked[et][1]:
            self._resolve_window(et)
        self._finished = True
        self.on_finished()

    # -- geometry (header pinned; editor + panels scroll in a viewport) -----
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("liveplay_content_top", 132)
        bottom = self.update_btn.rect.top - 8
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _content_w(self) -> int:
        return self._viewport().width - ScrollButtons.gutter()

    def _stat_step(self) -> int:
        return LAYOUT.i("liveplay_stat_row_h", 52) + LAYOUT.i("liveplay_stat_gap", 8)

    def _player_step(self) -> int:
        return LAYOUT.i("liveplay_player_row_h", 52) + LAYOUT.i("liveplay_player_gap", 8)

    def _y_stats(self) -> int:
        return LAYOUT.i("liveplay_section_gap", 30)

    def _y_cap_players(self) -> int:
        return self._y_stats() + len(_STATS) * self._stat_step()

    def _y_players(self) -> int:
        return self._y_cap_players() + LAYOUT.i("liveplay_section_gap", 30)

    def _y_locked_panel(self) -> int:
        return (self._y_players() + len(self.available) * self._player_step()
                + LAYOUT.i("liveplay_section_gap", 30))

    def _locked_line_count(self) -> int:
        # one title line + one line per locked window (predictions summarised on it)
        return 1 + len(self._locked)

    def _locked_panel_h(self) -> int:
        if not self._locked:
            return 0
        pad = LAYOUT.i("liveplay_panel_pad", 12)
        gap = LAYOUT.i("liveplay_panel_line_gap", 22)
        return pad * 2 + self._locked_line_count() * gap

    def _y_report(self) -> int:
        h = self._locked_panel_h()
        extra = (h + LAYOUT.i("liveplay_section_gap", 30)) if h else 0
        return self._y_locked_panel() + extra

    def _report_line_count(self) -> int:
        rep = self.last_report
        lines = 1 + 2 + len(rep.results)  # title + two meter lines + per-stat
        if rep.success_fired and rep.success_shot is not None:
            lines += 2
        if rep.concede_fired and rep.concede_shot is not None:
            lines += 2
        return lines

    def _report_h(self) -> int:
        if self.last_report is None:
            return 0
        pad = LAYOUT.i("liveplay_report_pad", 12)
        gap = LAYOUT.i("liveplay_report_line_gap", 22)
        return pad * 2 + self._report_line_count() * gap

    def _content_h(self) -> int:
        return self._y_report() + self._report_h() + 8

    def _max_scroll(self) -> int:
        return max(0, self._content_h() - self._viewport().height)

    def _to_screen(self, content_rect: pygame.Rect) -> pygame.Rect:
        vp = self._viewport()
        return content_rect.move(vp.x, vp.top - self.scroll)

    def _stat_rect(self, i: int) -> pygame.Rect:
        h = LAYOUT.i("liveplay_stat_row_h", 52)
        return self._to_screen(pygame.Rect(0, self._y_stats() + i * self._stat_step(),
                                           self._content_w(), h))

    def _player_rect(self, j: int) -> pygame.Rect:
        h = LAYOUT.i("liveplay_player_row_h", 52)
        return self._to_screen(pygame.Rect(0, self._y_players() + j * self._player_step(),
                                           self._content_w(), h))

    def _locked_panel_rect(self) -> pygame.Rect:
        return self._to_screen(pygame.Rect(0, self._y_locked_panel(),
                                           self._content_w(), self._locked_panel_h()))

    def _report_rect(self) -> pygame.Rect:
        return self._to_screen(pygame.Rect(0, self._y_report(),
                                           self._content_w(), self._report_h()))

    # -- input --------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_a):
            self._auto_pick()
            return
        if self.zoom_idx is not None:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.detail.select_btn.hit(event.pos):
                    self.active_id = self.available[self.zoom_idx].athlete_id
                    self.feedback = ""
                self.zoom_idx = None     # any tap (except a Select, above) closes
            return
        if event.type == pygame.MOUSEWHEEL:
            if self._viewport().collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0, min(self._max_scroll(), self.scroll - event.y * 40))
            return
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.update_btn.hit(event.pos):
            self._force_update()
            return
        if self.scroll_btns.contains(event.pos):
            self.scroll = self.scroll_btns.handle(event, self.scroll, self._max_scroll())
            return
        if not self._viewport().collidepoint(event.pos):
            return
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            if r.collidepoint(event.pos):
                self._tap_stat(s["code"], event.pos[0], r)
                return
        for j, ath in enumerate(self.available):
            if self._player_rect(j).collidepoint(event.pos):
                self.zoom_idx = j     # open the detail panel; Select there sets active
                return

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:           # "+" stepper
            self.lines[code] += 1
            self._arm(code)
        elif x > r.right - 112:        # "-" stepper
            self.lines[code] = max(0, self.lines[code] - 1)
            self._arm(code)
        else:                          # row body: toggle lock
            if code in self.locked:
                self.locked.discard(code)
            else:
                self.locked.add(code)
                self.touched.discard(code)
            self.feedback = ""

    def _arm(self, code: str) -> None:
        self.touched.add(code)
        self.locked.discard(code)
        self.feedback = ""

    def _auto_pick(self) -> None:
        self.locked = {s["code"] for s in _STATS}
        self.touched.clear()
        if self.available:
            self.active_id = self.available[0].athlete_id

    def _force_update(self) -> None:
        """Poll immediately. Followers read the cache, the lead triggers upstream -- the
        FeedClient already encodes is_lead, so we just fire the same poll path."""
        self._kick_poll(self.now_fn())

    # -- render -------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        now = self.now_fn()

        # Header: running match clock (from MatchClock, NOT the feed minute) + score/status.
        hf = font(LAYOUT.i("liveplay_header_size", 20))
        header = (f"{self.half_label}  -  Editing window {self.edit_window}"
                  if self.half_label else f"Editing window {self.edit_window}")
        surface.blit(hf.render(header, True, _C["accent"]),
                     (m, LAYOUT.i("liveplay_header_y", 16)))
        cf = font(LAYOUT.i("liveplay_clock_size", 30))
        surface.blit(cf.render(f"{self.mc.display_minute(now)}'", True, _C["accent"]),
                     (m, LAYOUT.i("liveplay_clock_y", 44)))
        sf = font(LAYOUT.i("liveplay_score_size", 17))
        score = f"{self.feed.home_team()} v {self.feed.away_team()}".strip(" v")
        status = self.feed.match_status()
        info = f"{score}  {status}".strip() if score else status
        surface.blit(sf.render(info, True, _C["text_dim"]),
                     (m + 70, LAYOUT.i("liveplay_score_y", 50)))
        if self.feedback:
            ff = font(LAYOUT.i("liveplay_hint_size", 15))
            surface.blit(ff.render(self.feedback, True, _C["red"]),
                         (m + 130, LAYOUT.i("liveplay_header_y", 16)))

        # Pre-kickoff lobby: countdown above the editor (editor still shown for W1 pre-set).
        if self._phase != PHASE_ACTIVE and self._secs is not None:
            lf = font(LAYOUT.i("liveplay_lobby_label_size", 22))
            s = lf.render(f"Kickoff in {format_minutes(self._secs)}", True, _C["red"])
            surface.blit(s, s.get_rect(midtop=(surface.get_width() // 2,
                                               LAYOUT.i("liveplay_lobby_label_y", 84))))

        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        self._draw_captions(surface)
        self._draw_stats(surface)
        self._draw_players(surface)
        self._draw_locked_panel(surface)
        self._draw_report(surface)
        surface.set_clip(prev)

        if self.zoom_idx is None and self._max_scroll() > 0:
            self.scroll_btns.draw(surface, self.scroll, self._max_scroll())
        if self.zoom_idx is None:
            self.update_btn.draw(surface, font(LAYOUT.i("liveplay_stat_size", 20)))
        else:
            ath = self.available[self.zoom_idx]
            self.detail.select_btn.label = (
                "Picked" if ath.athlete_id == self.active_id else "Pick player")
            self.detail.draw(surface, ath)

    def _draw_captions(self, surface: pygame.Surface) -> None:
        cf = font(LAYOUT.i("liveplay_section_size", 17))
        vp = self._viewport()
        x = vp.x + 4
        top1 = self._to_screen(pygame.Rect(0, 0, 0, 0)).y
        surface.blit(cf.render("Lock your predictions", True, _C["text_dim"]), (x, top1))
        top2 = self._to_screen(pygame.Rect(0, self._y_cap_players(), 0, 0)).y
        surface.blit(cf.render("Pick active player", True, _C["text_dim"]), (x, top2 + 6))

    def _draw_stats(self, surface: pygame.Surface) -> None:
        vp = self._viewport()
        sf = font(LAYOUT.i("liveplay_stat_size", 20))
        cr = LAYOUT.i("play_circle_r", 11)
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            code = s["code"]
            locked = code in self.locked
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            if locked:
                pygame.draw.rect(surface, _C["accent"], r, width=2, border_radius=8)
            color = (_C["green"] if locked
                     else _C["orange"] if code in self.touched else _C["red"])
            pygame.draw.circle(surface, color, (r.x + 22, r.centery), cr)
            surface.blit(sf.render(f"{s['label']}: {self.lines[code]}", True, _C["white"]),
                         (r.x + 44, r.y + 14))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 12))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 12))

    def _draw_players(self, surface: pygame.Surface) -> None:
        vp = self._viewport()
        sf = font(LAYOUT.i("liveplay_stat_size", 20))
        for j, ath in enumerate(self.available):
            r = self._player_rect(j)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            athlete_card(surface, r, sf, ath.name, ath.archetype,
                         ath.stars, ath.athlete_id == self.active_id)

    def _draw_locked_panel(self, surface: pygame.Surface) -> None:
        if not self._locked:
            return
        panel = self._locked_panel_rect()
        vp = self._viewport()
        if panel.bottom < vp.top or panel.top > vp.bottom:
            return
        pad = LAYOUT.i("liveplay_panel_pad", 12)
        gap = LAYOUT.i("liveplay_panel_line_gap", 22)
        pygame.draw.rect(surface, _C["surface"], panel, border_radius=8)
        pygame.draw.rect(surface, _C["border"], panel, width=2, border_radius=8)
        tf = font(LAYOUT.i("liveplay_panel_title_size", 18))
        lf = font(LAYOUT.i("liveplay_panel_line_size", 15))
        x = panel.x + pad
        y = panel.y + pad
        surface.blit(tf.render("Locked windows", True, _C["accent"]), (x, y))
        # newest-first; each stat's line number shown above its code (e.g. "goal 1")
        for w in sorted(self._locked, reverse=True):
            y += gap
            preds, active_id, _ = self._locked[w]
            picks = "  ".join(f"{p.stat_code} {p.line}" for p in preds) or "(none)"
            col = _C["text"] if active_id else _C["text_dim"]
            surface.blit(lf.render(f"W{w}: {picks}", True, col), (x, y))

    def _draw_report(self, surface: pygame.Surface) -> None:
        if self.last_report is None:
            return
        rep = self.last_report
        panel = self._report_rect()
        vp = self._viewport()
        if panel.bottom < vp.top or panel.top > vp.bottom:
            return
        pad = LAYOUT.i("liveplay_report_pad", 12)
        pygame.draw.rect(surface, _C["surface"], panel, border_radius=8)
        pygame.draw.rect(surface, _C["border"], panel, width=2, border_radius=8)
        tf = font(LAYOUT.i("liveplay_report_title_size", 18))
        lf = font(LAYOUT.i("liveplay_report_line_size", 15))
        x = panel.x + pad
        self._y = panel.y + pad

        surface.blit(tf.render(f"Window {rep.window} results", True, _C["accent"]),
                     (x, self._y))
        self._line(surface, lf, x,
                   f"Success meter {rep.success_pct}% "
                   f"({rep.success_value} of {rep.success_threshold})", _C["green"])
        if rep.success_fired and rep.success_shot is not None:
            self._shot_lines(surface, lf, x, rep.success_shot, "earned",
                             scored_label="GOAL!", missed_label="no goal",
                             scored_good=True)
        self._line(surface, lf, x,
                   f"Concede meter {rep.concede_pct}% "
                   f"({rep.concede_value} of {rep.concede_threshold})", _C["red"])
        if rep.concede_fired and rep.concede_shot is not None:
            self._shot_lines(surface, lf, x, rep.concede_shot, "conceded",
                             scored_label="GOAL against!", missed_label="no goal",
                             scored_good=False)
        for res in rep.results:
            if res.success_credit > 0:
                credit, col = f"+{res.success_credit} succ", _C["green"]
            elif res.concede_credit > 0:
                credit, col = f"+{res.concede_credit} conc", _C["red"]
            else:
                credit, col = "0", _C["text_dim"]
            self._line(surface, lf, x,
                       f"{res.label}: you {res.predicted} / was {res.actual}  "
                       f"{res.outcome.upper()}  {credit}", col)

    def _line(self, surface: pygame.Surface, f: pygame.font.Font, x: int,
              text: str, color: list[int]) -> None:
        self._y += LAYOUT.i("liveplay_report_line_gap", 22)
        surface.blit(f.render(text, True, color), (x, self._y))

    def _shot_lines(self, surface: pygame.Surface, f: pygame.font.Font, x: int,
                    shot, verb: str, scored_label: str, missed_label: str,
                    scored_good: bool) -> None:
        header_col = _C["green"] if verb == "earned" else _C["red"]
        self._line(surface, f, x, f">> 1 shot {verb}", header_col)
        if shot.archetype:
            role = f"{shot.archetype} {round(shot.conversion * 100)}%"
            who = f"{shot.shooter_name} ({role})"
        else:
            who = shot.shooter_name
        outcome = scored_label if shot.scored else missed_label
        good = shot.scored if scored_good else not shot.scored
        col = _C["green"] if good else _C["red"]
        self._line(surface, f, x + 12, f"{who}: {outcome}", col)
