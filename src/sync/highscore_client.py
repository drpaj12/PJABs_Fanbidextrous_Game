"""Post and read the per-game high-score board on the PHP relay (php/highscore.php).

Each client submits its own final scoreline (goals_for/goals_against) when a half ends;
the server appends it, ranks the board (goal difference, then goals-for), and keeps the
top entries per game. The board is a self-chosen handle + scoreline only -- no tokens, no
personal data -- so highscore.html can be a public read-only page.

Transport is injectable (same pattern as RelayClient/FeedClient) so tests use a fake and
the pygbag build uses the browser fetch backend.
"""
import json
from typing import Any
from src.sync.relay_client import Transport, default_transport


class HighscoreClient:
    def __init__(self, base_url: str, transport: Transport | None = None,
                 path: str = "/highscore.php") -> None:
        self._base = base_url.rstrip("/")
        self._path = path
        self._t = transport or default_transport()

    async def submit(self, game: str, username: str, goals_for: int,
                     goals_against: int) -> dict[str, Any]:
        """Append this player's final scoreline for `game` and return the updated board."""
        body = json.dumps({
            "game": game, "username": username,
            "goals_for": int(goals_for), "goals_against": int(goals_against),
        })
        return json.loads(await self._t.post(f"{self._base}{self._path}", body))

    async def board(self, game: str = "") -> dict[str, Any]:
        """Read the board for one game, or all games when `game` is empty."""
        url = f"{self._base}{self._path}"
        if game:
            from urllib.parse import quote
            url += f"?game={quote(game)}"
        return json.loads(await self._t.get(url))
