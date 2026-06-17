# src/ui/widgets.py
"""Mobile-friendly pygame widgets: large touch targets. All pygame lives in src/ui/."""
import pygame
from src.utils.constants import CONFIG

_C = CONFIG["colors"]


class Button:
    def __init__(self, rect: pygame.Rect, label: str) -> None:
        self.rect = rect
        self.label = label

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=12)
        pygame.draw.rect(surface, _C["border"], self.rect, width=2, border_radius=12)
        text = font.render(self.label, True, _C["text"])
        surface.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


class MeterBar:
    def __init__(self, rect: pygame.Rect, color: list[int]) -> None:
        self.rect = rect
        self.color = color

    def draw(self, surface: pygame.Surface, value: int, threshold: int) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=8)
        frac = 0 if threshold <= 0 else max(0.0, min(1.0, value / threshold))
        fill = self.rect.copy()
        fill.width = int(self.rect.width * frac)
        pygame.draw.rect(surface, self.color, fill, border_radius=8)


def athlete_card(surface: pygame.Surface, rect: pygame.Rect,
                 font: pygame.font.Font, name: str, archetype: str,
                 stars: int, selected: bool) -> None:
    bg = _C["accent"] if selected else _C["surface"]
    pygame.draw.rect(surface, bg, rect, border_radius=10)
    pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=10)
    surface.blit(font.render(name[:16], True, _C["white"]), (rect.x + 8, rect.y + 6))
    surface.blit(font.render(f"{archetype}  {'*' * stars}", True, _C["text_dim"]),
                 (rect.x + 8, rect.y + 30))
