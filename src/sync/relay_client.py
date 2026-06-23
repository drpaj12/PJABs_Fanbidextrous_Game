"""Async client for the room/token/action PHP relay (php/soccer_api.php).

Mirrors the proven MULTIPLAYER/baseball_api.php transport: query-string action + room + token,
JSON POST bodies tagged with a "type" field. Transport is injectable for tests and for the
pygbag/WASM fetch backend.
"""
import json
from typing import Any, Optional, Protocol


class Transport(Protocol):
    async def get(self, url: str) -> str: ...
    async def post(self, url: str, body: str) -> str: ...


class UrllibTransport:
    """Desktop/test transport. In pygbag, swap for a fetch-based transport."""
    async def get(self, url: str) -> str:
        import urllib.request
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read().decode("utf-8")

    async def post(self, url: str, body: str) -> str:
        import urllib.request
        req = urllib.request.Request(url, data=body.encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")


def default_transport() -> Transport:
    """Pick the right transport for the runtime: the browser's fetch() in pygbag/WASM
    (urllib has no sockets there), urllib everywhere else. FetchTransport is imported
    lazily so desktop and tests never touch the pygbag-only platform.window."""
    import sys
    if sys.platform == "emscripten":
        from src.sync.wasm_transport import FetchTransport
        return FetchTransport()
    return UrllibTransport()


class RelayClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 api_path: str = "/soccer_api.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = api_path
        self._t = transport or default_transport()

    def _url(self, action: str, room: int, token: str = "") -> str:
        url = f"{self._base}{self._path}?action={action}&room={room}"
        return url + (f"&token={token}" if token else "")

    async def list_rooms(self) -> dict[str, Any]:
        return json.loads(await self._t.get(f"{self._base}{self._path}?action=list"))

    async def join(self, room: int) -> dict[str, Any]:
        return json.loads(await self._t.post(self._url("join", room), "{}"))

    async def get_state(self, room: int, token: str) -> dict[str, Any]:
        return json.loads(await self._t.get(self._url("state", room, token)))

    async def heartbeat(self, room: int, token: str) -> dict[str, Any]:
        return json.loads(await self._t.post(self._url("heartbeat", room, token), "{}"))

    async def _update(self, room: int, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload)
        return json.loads(await self._t.post(self._url("update", room, token), body))

    async def submit_draft(self, room: int, token: str,
                           athlete_ids: list[str]) -> dict[str, Any]:
        return await self._update(room, token,
                                  {"type": "draft_submit", "athlete_ids": athlete_ids})

    async def submit_window(self, room: int, token: str, window: int,
                            predictions: list[str], active_id: str,
                            use_power: bool) -> dict[str, Any]:
        return await self._update(room, token, {
            "type": "window_submit", "window": window, "predictions": predictions,
            "active_id": active_id, "use_power": use_power,
        })

    async def submit_score_event(self, room: int, token: str, code: str) -> dict[str, Any]:
        return await self._update(room, token, {"type": "score_event", "code": code})

    # ------------------------------------------------------------------
    # Party methods (multi-player lobby; party identified by integer id)
    # ------------------------------------------------------------------

    def _party_url(self, action: str, party: int) -> str:
        return f"{self._base}{self._path}?action={action}&party={party}"

    async def party_join(self, party: int, username: str) -> dict[str, Any]:
        body = json.dumps({"type": "party_join", "username": username})
        return json.loads(await self._t.post(self._party_url("party_join", party), body))

    async def party_state(self, party: int) -> dict[str, Any]:
        return json.loads(await self._t.get(self._party_url("party_state", party)))

    async def party_pick(self, party: int, username: str, window: int,
                         preds: list[str], use: Optional[list[str]] = None) -> dict[str, Any]:
        body = json.dumps({"type": "party_pick", "username": username,
                           "window": window, "preds": preds, "use": list(use or [])})
        return json.loads(await self._t.post(self._party_url("party_pick", party), body))

    async def party_loadout(self, party: int, username: str, item_ids: list[str],
                            treasury: int) -> dict[str, Any]:
        body = json.dumps({"type": "party_loadout", "username": username,
                           "item_ids": item_ids, "treasury": treasury})
        return json.loads(await self._t.post(self._party_url("party_loadout", party), body))

    async def party_push(self, party: int, username: str,
                         state: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"type": "party_push", "username": username, **state})
        return json.loads(await self._t.post(self._party_url("party_push", party), body))
