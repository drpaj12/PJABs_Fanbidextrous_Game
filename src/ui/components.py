"""
components.py -- reusable UI widgets (buttons, labels, panels).

Keep these stateless where possible: pass in what to draw, draw it, return.
Build your game's specific screens in separate files inside src/ui/.
"""

import pygame
from typing import Optional, Callable


class Button:
    """A clickable rectangle with a text label."""

    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        font: pygame.font.Font,
        color_normal: tuple,
        color_hover: tuple,
        color_text: tuple,
        on_click: Optional[Callable] = None,
    ) -> None:
        self.rect         = rect
        self.label        = label
        self.font         = font
        self.color_normal = color_normal
        self.color_hover  = color_hover
        self.color_text   = color_text
        self.on_click     = on_click
        self._hovered     = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the button was clicked."""
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        color = self.color_hover if self._hovered else self.color_normal
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        text = self.font.render(self.label, True, self.color_text)
        text_rect = text.get_rect(center=self.rect.center)
        surface.blit(text, text_rect)


class Label:
    """A static text label."""

    def __init__(
        self,
        pos: tuple,
        text: str,
        font: pygame.font.Font,
        color: tuple,
        anchor: str = "topleft",
    ) -> None:
        self.pos    = pos
        self.text   = text
        self.font   = font
        self.color  = color
        self.anchor = anchor

    def draw(self, surface: pygame.Surface) -> None:
        rendered = self.font.render(self.text, True, self.color)
        rect = rendered.get_rect(**{self.anchor: self.pos})
        surface.blit(rendered, rect)

    def update_text(self, new_text: str) -> None:
        self.text = new_text


class Panel:
    """A filled rectangle, optionally with a border. Use as a background for card areas."""

    def __init__(
        self,
        rect: pygame.Rect,
        color_fill: tuple,
        color_border: Optional[tuple] = None,
        border_width: int = 1,
        border_radius: int = 6,
    ) -> None:
        self.rect          = rect
        self.color_fill    = color_fill
        self.color_border  = color_border
        self.border_width  = border_width
        self.border_radius = border_radius

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, self.color_fill, self.rect, border_radius=self.border_radius)
        if self.color_border:
            pygame.draw.rect(surface, self.color_border, self.rect,
                             width=self.border_width, border_radius=self.border_radius)
