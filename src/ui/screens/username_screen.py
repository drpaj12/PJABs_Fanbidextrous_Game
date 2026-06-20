# src/ui/screens/username_screen.py
"""Enter a username to start. on_submit(username) fires on Start / Enter.

The caller decides what the name means (the lead client triggers the live polling).
Text is captured via pygame TEXTINPUT so a phone's soft keyboard works; BACKSPACE and
RETURN are handled through KEYDOWN. A tappable Start button covers touch-only devices.
"""
from typing import TYPE_CHECKING, Callable

import pygame
from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_TITLE = CONFIG["display"]["title"]
_LEAD_NAME = CONFIG["client"]["lead_username"]
_MAX_LEN = 16


class UsernameScreen(Screen):
    def __init__(self, app: "App", on_submit: Callable[[str], None]) -> None:
        super().__init__(app)
        self.on_submit = on_submit
        self.text = ""
        self._submitted = False
        self._caret = 0.0
        sw = app.screen.get_width()
        bw = LAYOUT.i("fixsel_btn_w", 360)
        bh = LAYOUT.i("fixsel_btn_h", 72)
        x = (sw - bw) // 2
        self.field = pygame.Rect(x, LAYOUT.i("user_field_y", 330), bw, bh)
        self.start_btn = Button(
            pygame.Rect(x, LAYOUT.i("user_btn_y", 430), bw, bh), "Start")
        if hasattr(pygame.key, "start_text_input"):
            pygame.key.start_text_input()

    def handle(self, event: pygame.event.Event) -> None:
        if self._submitted:
            return
        if event.type == pygame.TEXTINPUT:
            if len(self.text) < _MAX_LEN and event.text.isprintable():
                self.text += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._submit()
            elif event.unicode and event.unicode.isprintable() \
                    and len(self.text) < _MAX_LEN and event.key != pygame.K_TAB:
                # Fallback for backends that send KEYDOWN.unicode but no TEXTINPUT.
                if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    self.text += event.unicode
        elif event.type == pygame.MOUSEBUTTONDOWN and self.start_btn.hit(event.pos):
            self._submit()

    def _submit(self) -> None:
        if self._submitted or not self.text.strip():
            return
        self._submitted = True
        if hasattr(pygame.key, "stop_text_input"):
            pygame.key.stop_text_input()
        self.on_submit(self.text.strip())

    def update(self, dt: float) -> None:
        self._caret = (self._caret + dt) % 1.0

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("fixsel_title_size", 30))
        t = tf.render(_TITLE, True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("fixsel_title_y", 150))))
        sf = font(LAYOUT.i("ui_body_size", 22))
        s = sf.render("Enter a username to start", True, _C["accent"])
        surface.blit(s, s.get_rect(center=(sw // 2, LAYOUT.i("fixsel_sub_y", 220))))
        # text field
        radius = LAYOUT.i("ui_btn_radius", 12)
        pygame.draw.rect(surface, _C["surface"], self.field, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], self.field, width=2, border_radius=radius)
        ff = font(LAYOUT.i("ui_body_size", 22) + 4)
        shown = self.text + ("|" if self._caret < 0.5 else "")
        tx = ff.render(shown or " ", True, _C["white"])
        surface.blit(tx, tx.get_rect(midleft=(self.field.x + 14, self.field.centery)))
        self.start_btn.draw(surface, sf)
        hint = font(LAYOUT.i("ui_small_size", 17))
        msg = f'"{_LEAD_NAME}" is the lead client -- it polls the live scores for everyone'
        h = hint.render(msg, True, _C["text_dim"])
        surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 50)))
