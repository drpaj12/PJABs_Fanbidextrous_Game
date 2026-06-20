# src/sync/local_store.py
"""Persistent key/value storage for the warm cache.

In the browser (pygbag/WASM) this is window.localStorage; on desktop it is a small JSON
file. Import-safe: `platform` is WASM-only and imported lazily, so importing this module on
desktop (and in tests) never touches it. Values are strings (the caller serialises).

Detection idiom matches wasm_transport.py: sys.platform == "emscripten".
"""
import json
import sys
from pathlib import Path
from typing import Optional


class LocalStore:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._is_web: bool = sys.platform == "emscripten"
        self._path: Optional[Path] = Path(file_path) if file_path is not None else None

    def get(self, key: str) -> Optional[str]:
        if self._is_web:
            import platform  # WASM-only
            return platform.window.localStorage.getItem(key)
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        if self._is_web:
            import platform  # WASM-only
            platform.window.localStorage.setItem(key, value)
            return
        data = self._read()
        data[key] = value
        self._write(data)

    # -- desktop JSON-file backend ----------------------------------------

    def _read(self) -> dict:
        if not self._path or not self._path.exists():
            return {}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, data: dict) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")
