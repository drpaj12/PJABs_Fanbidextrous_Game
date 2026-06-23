# src/ui/widgets.py
"""Mobile-friendly pygame widgets: large touch targets. All pygame lives in src/ui/."""
import math
import time

import pygame
from src.game import ability_text
from src.utils.asset_loader import load_icon
from src.utils.constants import CONFIG, LAYOUT

_C = CONFIG["colors"]


_USE_SYSFONT = True


def font(size: int) -> pygame.font.Font:
    """A font of the given pixel size.

    Tries the system 'arial' (nice on desktop), but the pygbag/WASM runtime ships no
    system fonts -- SysFont can raise or hang there -- so on first failure we switch
    permanently to pygame's built-in default font. Using the default font is the
    standard pygbag-safe choice; this keeps desktop crisp and the web build alive.
    """
    global _USE_SYSFONT
    if _USE_SYSFONT:
        try:
            return pygame.font.SysFont("arial", size)
        except Exception:
            _USE_SYSFONT = False
    return pygame.font.Font(None, size)


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


def wall_clock_str() -> str:
    """Local time of day as HH:MM. pygbag-safe -- uses strftime, never JS Date.now()."""
    return time.strftime("%H:%M")


def draw_match_banner(surface: pygame.Surface, scoreline: str, y: int,
                      clock: str = "") -> None:
    """Top banner: the actual match scoreline (+minute/status) left-aligned, and the real
    wall-clock time of day right-aligned, on the same row. `scoreline` is built by the screen
    from its feed (single-device) or `coord.view()['match']` (party)."""
    m = LAYOUT.i("screen_margin", 20)
    sf = font(LAYOUT.i("banner_score_size", 15))
    surface.blit(sf.render(scoreline, True, _C["text_dim"]), (m, y))
    if clock:
        cf = font(LAYOUT.i("banner_clock_size", 16))
        img = cf.render(clock, True, _C["accent"])
        surface.blit(img, (surface.get_width() - m - img.get_width(), y))


def wrap_text(text: str, f: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word-wrap `text` to lines that each render within `max_width` pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and f.size(trial)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def athlete_card(surface: pygame.Surface, rect: pygame.Rect,
                 name_font: pygame.font.Font, name: str, archetype: str,
                 stars: int, selected: bool, tagline: str = "") -> None:
    bg = _C["accent"] if selected else _C["surface"]
    radius = LAYOUT.i("ui_corner_radius", 10)
    pygame.draw.rect(surface, bg, rect, border_radius=radius)
    pygame.draw.rect(surface, _C["border"], rect, width=2, border_radius=radius)
    surface.blit(name_font.render(name[:16], True, _C["white"]), (rect.x + 8, rect.y + 6))
    surface.blit(name_font.render(f"{archetype}  {'*' * stars}", True, _C["text_dim"]),
                 (rect.x + 8, rect.y + 30))
    if tagline:
        tf = font(LAYOUT.i("card_tagline_size", 15))
        cap = LAYOUT.i("card_tagline_max", 34)
        text = tagline if len(tagline) <= cap else tagline[:cap - 3] + "..."
        surface.blit(tf.render(text, True, _C["accent"]),
                     (rect.x + 8, rect.y + 30 + LAYOUT.i("card_tagline_dy", 22)))


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
    """Scrollable list of short result lines inside a clip rect.

    Top-down model (oldest line at the top, newest at the bottom): `scroll` is a pixel offset
    in [0, max_scroll], 0 = top/oldest, max = bottom/newest. By default it sticks to the
    newest line, so the latest narrative is visible without scrolling; once the user scrolls
    up to read history the stick releases, and re-engages when they scroll back to the bottom.
    Pairs with a ScrollButtons in the owning screen (up = older, down = newer) for touch.
    """

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.entries: list[str] = []
        self.scroll = 0
        self._stick = True   # pin to the newest line until the user scrolls up

    def add(self, line: str) -> None:
        self.entries.append(line)

    def _line_h(self) -> int:
        return LAYOUT.i("play_log_line_size", 16) + 6

    def content_h(self) -> int:
        return len(self.entries) * self._line_h()

    def max_scroll(self) -> int:
        return max(0, self.content_h() - self.rect.height)

    def scroll_to(self, value: int) -> None:
        """Set the scroll offset (clamped); used by the ScrollButtons in the owning screen."""
        self.scroll = max(0, min(self.max_scroll(), value))
        self._stick = self.scroll >= self.max_scroll()

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll_to(self.scroll - event.y * 30)

    @staticmethod
    def _line_color(line: str) -> list[int]:
        """Color a crawl-log line by the outcome tokens the resolver embeds.

        The resolver tags each line: per-prediction lines end in a color word
        '(GREEN)'/'(ORANGE)'/'(RED)', gate lines say '-> PASS'/'-> FAIL', and a
        Power gain starts with 'POWER'. 'GOAL' lines stay accent (existing rule)."""
        stripped = line.strip()
        if "(RED)" in line or "BIG MISS" in line or "-> FAIL" in line or "downed" in line:
            return _C["red"]
        if "(GREEN)" in line:
            return _C["green"]
        if "(ORANGE)" in line:
            return _C["orange"]
        if "-> PASS" in line or stripped.startswith("POWER") or stripped.startswith("GOAL"):
            return _C["accent"]
        return _C["text"]

    def draw(self, surface: pygame.Surface) -> None:
        line_h = self._line_h()
        f = font(LAYOUT.i("play_log_line_size", 16))
        if self._stick:                       # keep the newest line pinned to the bottom
            self.scroll = self.max_scroll()
        prev = surface.get_clip()
        surface.set_clip(self.rect)
        y = self.rect.top - self.scroll       # oldest first, top-down
        for line in self.entries:
            if y > self.rect.bottom:
                break
            if y > self.rect.top - line_h:
                surface.blit(f.render(line, True, self._line_color(line)),
                             (self.rect.x + 4, y))
            y += line_h
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
        rf = font(LAYOUT.i("draft_detail_role_size", 18))
        gap = LAYOUT.i("draft_detail_line_gap", 32)
        x = self.rect.x + 16
        max_w = self.rect.width - 32
        y = self.rect.y + 16
        surface.blit(nf.render(athlete.name, True, _C["white"]), (x, y))
        y += gap + 8

        # Role read (wrapped, accent) -- the one-line 'why this player is good'.
        for line in wrap_text(ability_text.role_summary(athlete), rf, max_w):
            surface.blit(rf.render(line, True, _C["accent"]), (x, y))
            y += LAYOUT.i("draft_detail_role_gap", 26)
        y += 6

        # Compact identity block.
        for r in (f"Position: {athlete.broad_position}",
                  f"Team: {athlete.team}",
                  f"Jersey: {athlete.jersey}"):
            surface.blit(bf.render(r, True, _C["text"]), (x, y))
            y += gap
        y += 6

        # Abilities (this/next window effects, conversion %, rating).
        surface.blit(rf.render("Abilities", True, _C["text_dim"]), (x, y))
        y += LAYOUT.i("draft_detail_role_gap", 26)
        for line in ability_text.effect_lines(athlete):
            surface.blit(bf.render(line, True, _C["text"]), (x, y))
            y += gap

        self.select_btn.draw(surface, bf)


def item_effect_summary(item) -> str:
    """One-line human read of a shop item's effect (ASCII, for the detail panel)."""
    eff = item.effect
    value = int(eff.get("value", 0))
    if item.category == "weapon":
        return f"Weapon: +{value} to your party's gate rolls."
    if item.category == "armor":
        return f"Armor ({item.armor_slot}): soaks up to {value} damage on a failed gate."
    if item.category == "consumable":
        return f"Consumable: +{value} to one gate roll this window, then it is spent."
    if item.category == "magic":
        return f"Magic: {eff.get('option', 'boon')} -- a one-off party boon."
    return "A curious trinket."


class ItemDetail:
    """Zoomed detail panel for one shop item, with a Buy/Sell button (label set by caller)."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.action_btn = Button(
            pygame.Rect(rect.x + 16, rect.bottom - LAYOUT.i("draft_select_btn_h", 56) - 12,
                        rect.width - 32, LAYOUT.i("draft_select_btn_h", 56)),
            "Buy")

    def draw(self, surface: pygame.Surface, item, treasury: int) -> None:
        pygame.draw.rect(surface, _C["surface"], self.rect, border_radius=12)
        pygame.draw.rect(surface, _C["accent"], self.rect, width=2, border_radius=12)
        nf = font(LAYOUT.i("draft_detail_size", 22) + 4)
        bf = font(LAYOUT.i("draft_detail_size", 22))
        rf = font(LAYOUT.i("draft_detail_role_size", 18))
        gap = LAYOUT.i("draft_detail_line_gap", 32)
        x = self.rect.x + 16
        max_w = self.rect.width - 32
        y = self.rect.y + 16

        size = LAYOUT.i("shop_detail_icon", 56)
        icon = load_icon(item.category)
        icon_box = pygame.Rect(x, y, size, size)
        if icon is not None:
            surface.blit(pygame.transform.smoothscale(icon, (size, size)), icon_box)
        else:
            pygame.draw.rect(surface, _C["border"], icon_box, border_radius=8)
        for line in wrap_text(item.name, nf, max_w - size - 12)[:2]:
            surface.blit(nf.render(line, True, _C["white"]), (icon_box.right + 12, y))
            y += LAYOUT.i("draft_detail_role_gap", 26)
        y = max(y, icon_box.bottom) + 10

        surface.blit(bf.render(f"{item.category}  {'*' * item.stars}  {item.price}g",
                               True, _C["gold"]), (x, y))
        y += gap
        if item.armor_slot:
            surface.blit(bf.render(f"Slot: {item.armor_slot}", True, _C["text"]), (x, y))
            y += gap
        for line in wrap_text(item_effect_summary(item), rf, max_w):
            surface.blit(rf.render(line, True, _C["accent"]), (x, y))
            y += LAYOUT.i("draft_detail_role_gap", 26)
        y += 8
        surface.blit(bf.render(f"Your gold: {treasury}", True, _C["gold"]), (x, y))

        self.action_btn.draw(surface, bf)


def draw_depth_meter(surface: pygame.Surface, rect: pygame.Rect, depth: int,
                     total: int, gate_step: int, color_key: str) -> None:
    """A pip track of `total` cells inside `rect`. Cells 0..depth-1 fill in colors[color_key];
    the rest are dim. Every `gate_step`-th boundary cell is outlined in gold. A 'depth/total'
    caption renders just above the track."""
    cap_h = LAYOUT.i("depth_label_size", 14) + 4
    lf = font(LAYOUT.i("depth_label_size", 14))
    surface.blit(lf.render(f"Depth {depth}/{total}", True, _C["text_dim"]),
                 (rect.x, rect.y))
    track = pygame.Rect(rect.x, rect.y + cap_h, rect.width,
                        LAYOUT.i("depth_meter_h", 26))
    gap = LAYOUT.i("depth_pip_gap", 3)
    n = max(1, total)
    cell_w = max(2, (track.width - (n - 1) * gap) // n)
    fill = _C.get(color_key, _C["orange"])
    for i in range(n):
        x = track.x + i * (cell_w + gap)
        cell = pygame.Rect(x, track.y, cell_w, track.height)
        is_gate = gate_step > 0 and (i + 1) % gate_step == 0
        pygame.draw.rect(surface, fill if i < depth else _C["surface"], cell,
                         border_radius=3)
        if is_gate:
            pygame.draw.rect(surface, _C["gold"], cell, width=2, border_radius=3)
