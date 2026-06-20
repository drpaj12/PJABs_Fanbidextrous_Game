# src/utils/build_info.py
"""The build identifier (the apk basename) for the running client.

The web build writes the apk's name into config/build_id.txt at package time; this reads
it back so the UI can stamp it on screen. That stamp IS the apk filename, so a player and
I can both see at a glance which build a browser actually loaded -- the fastest way to
catch a stale cache. On desktop (no build step) the file is absent and this returns "dev".
"""
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_BUILD_FILE = _ROOT / "config" / "build_id.txt"


def build_id(path: Optional[Path] = None) -> str:
    """The build id (apk basename) from config/build_id.txt, or "dev" if it is missing or
    empty (e.g. a desktop dev run that never went through the web build)."""
    p = path if path is not None else _BUILD_FILE
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return "dev"
    return text or "dev"
