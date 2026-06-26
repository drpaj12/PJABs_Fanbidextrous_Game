# src/ui/screens/party_screen.py
"""Create Party / Join Party.

A party number (0..max_rooms-1) is chosen with a -/+ stepper and shared
out-of-band; the username comes from the upstream UsernameScreen. Both
buttons call on_done(party_number) -- party_join is create-or-join so they
behave identically. SIM auto-creates party 0.
"""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_MAX_ROOMS = int(CONFIG["party"]["max_rooms"])


class PartyScreen(Screen):
    def __init__(self, app: "App", username: str, on_done: Callable[[int], None],
                 sim: Optional[SimMode] = None,
                 on_clear: Optional[Callable[[int], None]] = None) -> None:
        super().__init__(app)
        self.username = username
        self.on_done = on_done
        self.sim = sim
        # on_clear (api-lead only) wipes the chosen party's server state. None for followers,
        # who never own the shared blob. Cleared via a two-tap confirm to prevent a fat-finger
        # wipe of an in-progress game.
        self.on_clear = on_clear
        self.party_number = 0
        self._done = False
        self._clear_armed = False
        self._cleared = False

        sw = app.screen.get_width()
        bw = LAYOUT.i("party_btn_w", 320)
        bh = LAYOUT.i("party_btn_h", 64)
        gap = LAYOUT.i("party_btn_gap", 20)
        y = LAYOUT.i("party_btn_y", 380)
        x = (sw - bw) // 2
        self.create_btn = Button(pygame.Rect(x, y, bw, bh), "Create Party")
        self.join_btn = Button(pygame.Rect(x, y + bh + gap, bw, bh), "Join Party")
        self.clear_btn = Button(pygame.Rect(x, y + 2 * (bh + gap), bw, bh),
                                "Clear server state")

        sttop = LAYOUT.i("party_num_y", 250)
        stw = LAYOUT.i("party_stepper_w", 64)
        stgap = LAYOUT.i("party_stepper_gap", 120)
        cx = sw // 2
        self.minus_btn = Button(pygame.Rect(cx - stgap, sttop, stw, stw), "-")
        self.plus_btn = Button(pygame.Rect(cx + stgap - stw, sttop, stw, stw), "+")

    def handle(self, event: pygame.event.Event) -> None:
        if self._done or event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.minus_btn.hit(event.pos):
            self.party_number = (self.party_number - 1) % _MAX_ROOMS
            self._clear_armed = self._cleared = False    # changing party re-arms the confirm
        elif self.plus_btn.hit(event.pos):
            self.party_number = (self.party_number + 1) % _MAX_ROOMS
            self._clear_armed = self._cleared = False
        elif self.on_clear is not None and self.clear_btn.hit(event.pos):
            self._handle_clear()
        elif self.create_btn.hit(event.pos) or self.join_btn.hit(event.pos):
            self._finish()

    def _handle_clear(self) -> None:
        """Two-tap confirm: first tap arms, second tap wipes the party's server state."""
        if not self._clear_armed:
            self._clear_armed = True
            return
        self.on_clear(self.party_number)
        self._clear_armed = False
        self._cleared = True

    def _finish(self) -> None:
        self._done = True
        self.on_done(self.party_number)

    def update(self, dt: float) -> None:
        if not self._done and self.sim and self.sim.enabled:
            self._finish()

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("party_title_size", 30))
        t = tf.render("Dungeon Party", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("party_title_y", 110))))

        sf = font(LAYOUT.i("party_sub_size", 17))
        sub = sf.render(f"Playing as {self.username}", True, _C["accent"])
        surface.blit(sub, sub.get_rect(center=(sw // 2, LAYOUT.i("party_sub_y", 168))))

        lf = font(LAYOUT.i("party_num_label_size", 20))
        lab = lf.render("Party number", True, _C["text_dim"])
        surface.blit(lab, lab.get_rect(center=(sw // 2, LAYOUT.i("party_num_y", 250) - 30)))

        nf = font(LAYOUT.i("party_num_value_size", 40))
        val = nf.render(str(self.party_number), True, _C["white"])
        surface.blit(val, val.get_rect(center=(
            sw // 2,
            LAYOUT.i("party_num_y", 250) + LAYOUT.i("party_stepper_w", 64) // 2
        )))

        bf = font(LAYOUT.i("party_num_label_size", 20))
        for b in (self.minus_btn, self.plus_btn, self.create_btn, self.join_btn):
            b.draw(surface, bf)

        if self.on_clear is not None:
            if self._cleared:
                self.clear_btn.label = "Server state cleared"
            elif self._clear_armed:
                self.clear_btn.label = "Tap again to confirm"
            else:
                self.clear_btn.label = "Clear server state"
            self.clear_btn.draw(surface, bf)
