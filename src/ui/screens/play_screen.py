# src/ui/screens/play_screen.py
"""Play screen: predict every stat, lock each one in, then resolve the window.

Each of the five stats has a status light: RED (untouched) -> ORANGE (adjusting with
-/+) -> GREEN (locked in). Tap a stat's row to toggle its lock; tap -/+ to move its line
(which re-arms it to orange). Pick one active player for the window, then press the bottom
button to resolve -- any locked subset is allowed. A results panel at the foot shows how the
LAST window landed: both meter fill percentages and, per prediction, how close the line was
and the credit it fed into the success/concede meters.

on_submit(preds: list[Prediction], active_id: str, use_power: bool) fires on resolve.
The countdown is cosmetic in single-device play; it does not force submission.

Mobile layout: the header and resolve button are pinned. The stat rows, the player picker,
and the results panel live in a clipped viewport that scrolls via the on-screen up/down
buttons (or the mouse wheel on desktop), so every control is reachable on a 414x896 canvas.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, ScrollButtons, athlete_card, font
from src.game.prediction import Prediction
from src.game.athlete import DraftedAthlete
from src.game.window_report import WindowReport
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]


class PlayScreen(Screen):
    def __init__(self, app: "App", available: list[DraftedAthlete],
                 on_submit: Callable[..., None], window: int,
                 sim: Optional[SimMode] = None,
                 last_report: Optional[WindowReport] = None) -> None:
        super().__init__(app)
        self.available = available
        self.on_submit = on_submit
        self.window = window
        self.sim = sim
        self.last_report = last_report
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self.locked: set[str] = set()    # green: committed for this window
        self.touched: set[str] = set()   # orange: adjusted but not yet locked
        self.active_id: str | None = None
        self.use_power = False
        self.feedback = ""
        self.remaining = float(CONFIG["game"]["window_seconds"])
        self.scroll = 0
        self._y = 0  # render cursor for the results panel (set each draw)
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.lock_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("play_lock_btn_h", 56) - 12,
                        sw - 2 * m, LAYOUT.i("play_lock_btn_h", 56)),
            "Lock window")
        self.scroll_btns = ScrollButtons(self._viewport())

    # -- geometry: header + resolve button are pinned; the rest scrolls in a viewport --
    def _viewport(self) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("play_content_top", 88)
        bottom = self.lock_btn.rect.top - 8
        return pygame.Rect(m, top, self.app.screen.get_width() - 2 * m, bottom - top)

    def _content_w(self) -> int:
        return self._viewport().width - ScrollButtons.gutter()

    def _stat_step(self) -> int:
        return LAYOUT.i("play_stat_row_h", 52) + LAYOUT.i("play_stat_gap", 8)

    def _player_step(self) -> int:
        return LAYOUT.i("play_player_row_h", 52) + LAYOUT.i("play_player_gap", 8)

    # content-space y offsets (before the viewport/scroll transform)
    def _y_stats(self) -> int:
        return LAYOUT.i("play_section_gap", 30)

    def _y_cap_players(self) -> int:
        return self._y_stats() + len(_STATS) * self._stat_step()

    def _y_players(self) -> int:
        return self._y_cap_players() + LAYOUT.i("play_section_gap", 30)

    def _y_report(self) -> int:
        return (self._y_players() + len(self.available) * self._player_step()
                + LAYOUT.i("play_section_gap", 30))

    def _report_line_count(self) -> int:
        """Title + each meter line + (2 lines per fired meter's shot) + per-stat lines."""
        rep = self.last_report
        lines = 1 + 2 + len(rep.results)  # title + the two meter lines + per-stat
        if rep.success_fired and rep.success_shot is not None:
            lines += 2  # ">> 1 shot earned" + the shooter line
        if rep.concede_fired and rep.concede_shot is not None:
            lines += 2  # ">> 1 shot conceded" + the shooter line
        return lines

    def _report_h(self) -> int:
        if self.last_report is None:
            return 0
        pad = LAYOUT.i("play_report_pad", 12)
        gap = LAYOUT.i("play_report_line_gap", 22)
        return pad * 2 + self._report_line_count() * gap

    def _content_h(self) -> int:
        return self._y_report() + self._report_h() + 8

    def _max_scroll(self) -> int:
        return max(0, self._content_h() - self._viewport().height)

    def _to_screen(self, content_rect: pygame.Rect) -> pygame.Rect:
        vp = self._viewport()
        return content_rect.move(vp.x, vp.top - self.scroll)

    def _stat_rect(self, i: int) -> pygame.Rect:
        h = LAYOUT.i("play_stat_row_h", 52)
        return self._to_screen(pygame.Rect(0, self._y_stats() + i * self._stat_step(),
                                           self._content_w(), h))

    def _player_rect(self, j: int) -> pygame.Rect:
        h = LAYOUT.i("play_player_row_h", 52)
        return self._to_screen(pygame.Rect(0, self._y_players() + j * self._player_step(),
                                           self._content_w(), h))

    def _report_rect(self) -> pygame.Rect:
        return self._to_screen(pygame.Rect(0, self._y_report(),
                                           self._content_w(), self._report_h()))

    # -- input --
    def handle(self, event: pygame.event.Event) -> None:
        if self.sim and self.sim.is_key(event, pygame.K_a):
            self._auto_pick()
            return
        if self.sim and self.sim.is_key(event, pygame.K_f):
            self._auto_pick()
            self._submit()
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
        if self.lock_btn.hit(event.pos):
            self._submit()
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
                self.active_id = ath.athlete_id
                self.feedback = ""
                return

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:           # the "+" stepper
            self.lines[code] += 1
            self._arm(code)
        elif x > r.right - 112:        # the "-" stepper
            self.lines[code] = max(0, self.lines[code] - 1)
            self._arm(code)
        else:                          # the row body: toggle the lock
            if code in self.locked:
                self.locked.discard(code)
            else:
                self.locked.add(code)
                self.touched.discard(code)
            self.feedback = ""

    def _arm(self, code: str) -> None:
        """Adjusting a line marks it orange and clears any prior lock on it."""
        self.touched.add(code)
        self.locked.discard(code)
        self.feedback = ""

    def _auto_pick(self) -> None:
        self.locked = {s["code"] for s in _STATS}
        self.touched.clear()
        self.active_id = self.available[0].athlete_id

    def _submit(self) -> None:
        if not self.active_id:
            self.feedback = "Pick an active player first."
            return
        if not self.locked:
            self.feedback = "Lock at least one stat (tap a row)."
            return
        preds = [Prediction(s["code"], self.lines[s["code"]])
                 for s in _STATS if s["code"] in self.locked]
        self.on_submit(preds, self.active_id, self.use_power)

    def update(self, dt: float) -> None:
        self.remaining = max(0.0, self.remaining - dt)
        self.lock_btn.label = f"Lock window ({len(self.locked)}/{len(_STATS)})"

    # -- render --
    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        hf = font(LAYOUT.i("play_window_size", 20))
        surface.blit(hf.render(f"Window {self.window}", True, _C["text_dim"]), (m, 16))
        tf = font(LAYOUT.i("play_timer_size", 30))
        mm, ss = divmod(int(self.remaining), 60)
        surface.blit(tf.render(f"{mm}:{ss:02d}", True, _C["accent"]), (m, 44))
        if self.feedback:
            ff = font(LAYOUT.i("play_hint_size", 15))
            surface.blit(ff.render(self.feedback, True, _C["red"]), (m + 110, 24))

        vp = self._viewport()
        prev = surface.get_clip()
        surface.set_clip(vp)
        self._draw_captions(surface)
        self._draw_stats(surface)
        self._draw_players(surface)
        self._draw_report(surface)
        surface.set_clip(prev)

        if self._max_scroll() > 0:
            self.scroll_btns.draw(surface, self.scroll, self._max_scroll())
        self.lock_btn.draw(surface, font(LAYOUT.i("play_stat_size", 20)))

    def _draw_captions(self, surface: pygame.Surface) -> None:
        cf = font(LAYOUT.i("play_section_size", 17))
        vp = self._viewport()
        x = vp.x + 4
        top1 = self._to_screen(pygame.Rect(0, 0, 0, 0)).y
        surface.blit(cf.render("Lock your predictions", True, _C["text_dim"]), (x, top1))
        top2 = self._to_screen(pygame.Rect(0, self._y_cap_players(), 0, 0)).y
        surface.blit(cf.render("Pick active player", True, _C["text_dim"]), (x, top2 + 6))

    def _draw_stats(self, surface: pygame.Surface) -> None:
        vp = self._viewport()
        sf = font(LAYOUT.i("play_stat_size", 20))
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
        sf = font(LAYOUT.i("play_stat_size", 20))
        for j, ath in enumerate(self.available):
            r = self._player_rect(j)
            if r.bottom < vp.top or r.top > vp.bottom:
                continue
            athlete_card(surface, r, sf, ath.name, ath.archetype,
                         ath.stars, ath.athlete_id == self.active_id)

    def _draw_report(self, surface: pygame.Surface) -> None:
        if self.last_report is None:
            return
        rep = self.last_report
        panel = self._report_rect()
        if panel.bottom < self._viewport().top or panel.top > self._viewport().bottom:
            return
        pad = LAYOUT.i("play_report_pad", 12)
        gap = LAYOUT.i("play_report_line_gap", 22)
        pygame.draw.rect(surface, _C["surface"], panel, border_radius=8)
        pygame.draw.rect(surface, _C["border"], panel, width=2, border_radius=8)
        tf = font(LAYOUT.i("play_report_title_size", 18))
        lf = font(LAYOUT.i("play_report_line_size", 15))
        x = panel.x + pad
        self._y = panel.y + pad

        surface.blit(tf.render(f"Window {rep.window} results", True, _C["accent"]),
                     (x, self._y))

        # Success meter, then the shot it earned (if it fired).
        self._line(surface, lf, x,
                   f"Success meter {rep.success_pct}% "
                   f"({rep.success_value} of {rep.success_threshold})", _C["green"])
        if rep.success_fired and rep.success_shot is not None:
            self._shot_lines(surface, lf, x, rep.success_shot, "earned",
                             scored_label="GOAL!", missed_label="no goal",
                             scored_good=True)

        # Concede meter, then the shot conceded (if it fired).
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
        self._y += LAYOUT.i("play_report_line_gap", 22)
        surface.blit(f.render(text, True, color), (x, self._y))

    def _shot_lines(self, surface: pygame.Surface, f: pygame.font.Font, x: int,
                    shot, verb: str, scored_label: str, missed_label: str,
                    scored_good: bool) -> None:
        """A '>> 1 shot <verb>' header plus the shooter line (red on the bad outcome)."""
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
