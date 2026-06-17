# src/ui/widgets.py
"""Mobile-friendly pygame widgets: large touch targets. All pygame lives in src/ui/."""
import pygame
from src.utils.constants import CONFIG, LAYOUT

_C = CONFIG["colors"]


def font(size: int) -> pygame.font.Font:
    """A SysFont of the given pixel size (cached by pygame internally)."""
    return pygame.font.SysFont("arial", size)


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

    def draw(self, surface: pygame.Surface, value: int, threshold: int,
             explode: float = 0.0) -> None:
        """explode in [0,1]: 0 = normal; >0 draws a white flash + radial lines."""
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=8)
        frac = 0 if threshold <= 0 else max(0.0, min(1.0, value / threshold))
        fill = self.rect.copy()
        fill.width = int(self.rect.width * frac)
        pygame.draw.rect(surface, self.color, fill, border_radius=8)
        if explode > 0.0:
            flash = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            flash.fill((*_C["white"], int(200 * explode)))
            surface.blit(flash, self.rect.topleft)
            cx, cy = self.rect.center
            for k in range(8):
                ang = k * 0.7853981633974483       # pi/4
                import math
                dx = int(math.cos(ang) * 30 * explode)
                dy = int(math.sin(ang) * 30 * explode)
                pygame.draw.line(surface, _C["white"], (cx, cy),
                                 (cx + dx, cy + dy), 2)


def athlete_card(surface: pygame.Surface, rect: pygame.Rect,
                 font: pygame.font.Font, name: str, archetype: str,
                 stars: int, selected: bool) -> None:
    bg = _C["accent"] if selected else _C["surface"]
    pygame.draw.rect(surface, bg, rect, border_radius=10)
    pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=10)
    surface.blit(font.render(name[:16], True, _C["white"]), (rect.x + 8, rect.y + 6))
    surface.blit(font.render(f"{archetype}  {'*' * stars}", True, _C["text_dim"]),
                 (rect.x + 8, rect.y + 30))


class Popup:
    """Centered modal panel listing text lines. Tap anywhere dismisses (caller-handled)."""

    def __init__(self, title: str, lines: list[str]) -> None:
        self.title = title
        self.lines = lines

    def draw(self, surface: pygame.Surface) -> None:
        sw, sh = surface.get_size()
        w = LAYOUT.i("popup_w", 340)
        pad = LAYOUT.i("popup_pad", 18)
        line_h = LAYOUT.i("popup_line_size", 18) + 8
        h = pad * 2 + 40 + len(self.lines) * line_h
        rect = pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, _C["surface"], rect, border_radius=12)
        pygame.draw.rect(surface, _C["accent"], rect, width=2, border_radius=12)
        tf = font(LAYOUT.i("popup_title_size", 24))
        surface.blit(tf.render(self.title, True, _C["accent"]),
                     (rect.x + pad, rect.y + pad))
        lf = font(LAYOUT.i("popup_line_size", 18))
        for i, line in enumerate(self.lines):
            surface.blit(lf.render(line, True, _C["text"]),
                         (rect.x + pad, rect.y + pad + 40 + i * line_h))


class LogList:
    """Scrollable list of short result lines inside a clip rect (newest at bottom)."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.entries: list[str] = []
        self.scroll = 0

    def add(self, line: str) -> None:
        self.entries.append(line)

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll = max(0, self.scroll - event.y * 30)

    def draw(self, surface: pygame.Surface) -> None:
        line_h = LAYOUT.i("play_log_line_size", 16) + 6
        f = font(LAYOUT.i("play_log_line_size", 16))
        prev = surface.get_clip()
        surface.set_clip(self.rect)
        y = self.rect.bottom - line_h + self.scroll
        for line in reversed(self.entries):
            if y < self.rect.top - line_h:
                break
            color = _C["accent"] if line.startswith("GOAL") else _C["text"]
            surface.blit(f.render(line, True, color), (self.rect.x + 4, y))
            y -= line_h
        surface.set_clip(prev)


class PlayerDetail:
    """Zoomed detail panel for one drafted athlete, with a Select button."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.select_btn = Button(
            pygame.Rect(rect.x + 16, rect.bottom - LAYOUT.i("draft_select_btn_h", 56) - 12,
                        rect.width - 32, LAYOUT.i("draft_select_btn_h", 56)),
            "Select")

    def draw(self, surface: pygame.Surface, athlete) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=12)
        pygame.draw.rect(surface, _C["accent"], self.rect, width=2, border_radius=12)
        nf = font(LAYOUT.i("draft_detail_size", 22) + 6)
        bf = font(LAYOUT.i("draft_detail_size", 22))
        x, y = self.rect.x + 16, self.rect.y + 16
        surface.blit(nf.render(athlete.name, True, _C["white"]), (x, y))
        rows = [f"Position: {athlete.broad_position}",
                f"Team: {athlete.team}",
                f"Archetype: {athlete.archetype}",
                f"Rating: {'*' * athlete.stars}",
                f"Jersey: {athlete.jersey}"]
        for i, r in enumerate(rows):
            surface.blit(bf.render(r, True, _C["text"]), (x, y + 44 + i * 34))
        self.select_btn.draw(surface, bf)
