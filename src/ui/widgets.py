# src/ui/widgets.py
"""Mobile-friendly pygame widgets: large touch targets. All pygame lives in src/ui/."""
import math
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
        radius = LAYOUT.i("ui_btn_radius", 12)
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], self.rect, width=2, border_radius=radius)
        text = font.render(self.label, True, _C["text"])
        surface.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


class ScrollButtons:
    """Pinned up/down scroll controls for touch lists (no mouse wheel on a phone).

    Lives in a right-edge gutter of `viewport`; the owning screen keeps the scroll
    offset and narrows its list content by `gutter()` so rows do not sit under the
    buttons. The buttons draw as triangles and dim at the scroll bounds.
    """

    def __init__(self, viewport: pygame.Rect) -> None:
        size = LAYOUT.i("ui_scroll_btn", 44)
        x = viewport.right - size
        self.up = pygame.Rect(x, viewport.top, size, size)
        self.down = pygame.Rect(x, viewport.bottom - size, size, size)
        self.step = LAYOUT.i("ui_scroll_step", 90)

    @staticmethod
    def gutter() -> int:
        return LAYOUT.i("ui_scroll_gutter", 52)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.up.collidepoint(pos) or self.down.collidepoint(pos)

    def handle(self, event: pygame.event.Event, scroll: int, max_scroll: int) -> int:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.up.collidepoint(event.pos):
                return max(0, scroll - self.step)
            if self.down.collidepoint(event.pos):
                return min(max_scroll, scroll + self.step)
        return scroll

    def draw(self, surface: pygame.Surface, scroll: int, max_scroll: int) -> None:
        self._arrow(surface, self.up, True, scroll > 0)
        self._arrow(surface, self.down, False, scroll < max_scroll)

    def _arrow(self, surface: pygame.Surface, rect: pygame.Rect,
               up: bool, enabled: bool) -> None:
        radius = LAYOUT.i("ui_btn_radius", 12)
        pygame.draw.rect(surface, _C["surface"], rect, border_radius=radius)
        pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)
        col = _C["accent"] if enabled else _C["text_dim"]
        cx, cy = rect.center
        d = rect.width // 5
        if up:
            pts = [(cx, cy - d), (cx - d, cy + d), (cx + d, cy + d)]
        else:
            pts = [(cx, cy + d), (cx - d, cy - d), (cx + d, cy - d)]
        pygame.draw.polygon(surface, col, pts)


class MeterBar:
    def __init__(self, rect: pygame.Rect, color: list[int]) -> None:
        self.rect = rect
        self.color = color

    def draw(self, surface: pygame.Surface, value: int, threshold: int,
             explode: float = 0.0) -> None:
        """explode in [0,1]: 0 = normal; >0 draws a white flash + radial lines."""
        radius = LAYOUT.i("ui_meter_radius", 8)
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=radius)
        frac = 0 if threshold <= 0 else max(0.0, min(1.0, value / threshold))
        fill = self.rect.copy()
        fill.width = int(self.rect.width * frac)
        pygame.draw.rect(surface, self.color, fill, border_radius=radius)
        if explode > 0.0:
            flash = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            flash.fill((*_C["white"], int(200 * explode)))
            surface.blit(flash, self.rect.topleft)
            cx, cy = self.rect.center
            for k in range(8):
                ang = k * (math.pi / 4)
                dx = int(math.cos(ang) * 30 * explode)
                dy = int(math.sin(ang) * 30 * explode)
                pygame.draw.line(surface, _C["white"], (cx, cy),
                                 (cx + dx, cy + dy), 2)


def athlete_card(surface: pygame.Surface, rect: pygame.Rect,
                 font: pygame.font.Font, name: str, archetype: str,
                 stars: int, selected: bool) -> None:
    bg = _C["accent"] if selected else _C["surface"]
    radius = LAYOUT.i("ui_corner_radius", 10)
    pygame.draw.rect(surface, bg, rect, border_radius=radius)
    pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)
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
        radius = LAYOUT.i("ui_btn_radius", 12)
        pygame.draw.rect(surface, _C["surface"], rect, border_radius=radius)
        pygame.draw.rect(surface, _C["accent"], rect, width=2, border_radius=radius)
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
