# src/utils/asset_loader.py
"""Lazy, cached image loading for the UI. Returns None when a file is absent so callers
fall back to a drawn primitive (keeps the web build alive if an icon is missing).

Icons live at <repo>/assets/images/icons/<name>.png (config assets.image_dir / icon_subdir).
Names used by the dungeon UI: weapon, armor, consumable, magic, tile, gate, monster,
power, wound."""
from pathlib import Path
from typing import Optional

import pygame

from src.utils.constants import CONFIG

_ROOT = Path(__file__).resolve().parents[2]
_ICON_DIR = _ROOT / CONFIG["assets"]["image_dir"] / CONFIG["assets"]["icon_subdir"]
_CACHE: dict[str, Optional[pygame.Surface]] = {}


def load_icon(name: str) -> Optional[pygame.Surface]:
    """Return the cached icon Surface for `name`, or None if the file is missing/unloadable."""
    if name in _CACHE:
        return _CACHE[name]
    path = _ICON_DIR / f"{name}.png"
    surf: Optional[pygame.Surface] = None
    if path.exists():
        try:
            loaded = pygame.image.load(str(path))
            try:
                surf = loaded.convert_alpha()   # fast blits once a display exists
            except pygame.error:
                surf = loaded                    # no display yet -- use the raw surface
        except pygame.error:
            surf = None
    _CACHE[name] = surf
    return surf
