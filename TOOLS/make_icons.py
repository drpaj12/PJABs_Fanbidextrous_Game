# TOOLS/make_icons.py
"""Generate the dungeon icon set as simple 64x64 PNGs using pygame primitives.

Run:  .venv/Scripts/python TOOLS/make_icons.py
Writes:  assets/images/icons/{weapon,armor,consumable,magic,tile,gate,monster,power,wound}.png

ASCII-only output. Headless (SDL dummy driver) so it needs no display."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

# Ensure the repo root is on sys.path so `src` is importable when this script
# is run directly (e.g. .venv/Scripts/python TOOLS/make_icons.py).
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pygame  # noqa: E402

from src.utils.constants import CONFIG  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / CONFIG["assets"]["image_dir"] / CONFIG["assets"]["icon_subdir"]
_C = CONFIG["colors"]
_SIZE = 64
_PAD = 8


def _surf() -> pygame.Surface:
    return pygame.Surface((_SIZE, _SIZE), pygame.SRCALPHA)


def _weapon() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["red"], [(32, 6), (40, 44), (24, 44)])      # blade
    pygame.draw.rect(s, _C["white"], (28, 44, 8, 14))                      # grip
    pygame.draw.rect(s, _C["white"], (20, 42, 24, 4))                      # cross-guard
    return s


def _armor() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["green"],
                        [(12, 12), (52, 12), (52, 36), (32, 56), (12, 36)])
    pygame.draw.polygon(s, _C["white"],
                        [(12, 12), (52, 12), (52, 36), (32, 56), (12, 36)], 3)
    return s


def _consumable() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["white"], (28, 8, 8, 10))                       # neck
    pygame.draw.circle(s, _C["orange"], (32, 40), 18)                      # flask
    pygame.draw.circle(s, _C["white"], (32, 40), 18, 3)
    return s


def _magic() -> pygame.Surface:
    s = _surf()
    pygame.draw.polygon(s, _C["accent"], [(32, 8), (56, 32), (32, 56), (8, 32)])
    pygame.draw.polygon(s, _C["white"], [(32, 8), (56, 32), (32, 56), (8, 32)], 3)
    return s


def _tile() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["border"], (_PAD, _PAD, _SIZE - 2 * _PAD, _SIZE - 2 * _PAD),
                     border_radius=6)
    return s


def _gate() -> pygame.Surface:
    s = _surf()
    pygame.draw.rect(s, _C["gold"], (12, 20, 40, 38))
    pygame.draw.circle(s, _C["gold"], (32, 20), 20)
    pygame.draw.rect(s, _C["background"], (24, 30, 16, 28))               # archway
    pygame.draw.circle(s, _C["background"], (32, 30), 8)
    return s


def _monster() -> pygame.Surface:
    s = _surf()
    pygame.draw.circle(s, _C["red"], (32, 34), 22)
    pygame.draw.circle(s, _C["white"], (24, 30), 5)
    pygame.draw.circle(s, _C["white"], (40, 30), 5)
    pygame.draw.circle(s, _C["background"], (24, 30), 2)
    pygame.draw.circle(s, _C["background"], (40, 30), 2)
    return s


def _power() -> pygame.Surface:
    s = _surf()
    pts = [(32, 6), (39, 26), (60, 26), (43, 39), (49, 59),
           (32, 47), (15, 59), (21, 39), (4, 26), (25, 26)]
    pygame.draw.polygon(s, _C["gold"], pts)
    return s


def _wound() -> pygame.Surface:
    s = _surf()
    pygame.draw.line(s, _C["red"], (14, 14), (50, 50), 8)
    pygame.draw.line(s, _C["red"], (50, 14), (14, 50), 8)
    return s


_ICONS = {
    "weapon": _weapon, "armor": _armor, "consumable": _consumable, "magic": _magic,
    "tile": _tile, "gate": _gate, "monster": _monster, "power": _power, "wound": _wound,
}


def main() -> None:
    pygame.init()
    _OUT.mkdir(parents=True, exist_ok=True)
    for name, builder in _ICONS.items():
        path = _OUT / f"{name}.png"
        pygame.image.save(builder(), str(path))
        print(f"OK wrote {path}")
    print(f"OK {len(_ICONS)} icons written to {_OUT}")


if __name__ == "__main__":
    main()
