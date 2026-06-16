"""
GameState -- the single source of truth for everything happening in the game.

Rules:
- No pygame imports here, ever.
- No rendering, no drawing, no screen coordinates.
- This module must be fully testable with plain pytest (no display required).
- All config values come from utils/constants.py, not hardcoded here.
"""

from dataclasses import dataclass
from typing import Optional
from src.utils.constants import CONFIG


@dataclass
class Player:
    name: str
    score: int = 0
    health: int = 0  # set from CONFIG in GameState.__init__

    def is_alive(self) -> bool:
        return self.health > 0

    def take_damage(self, amount: int) -> None:
        self.health = max(0, self.health - amount)

    def add_score(self, points: int) -> None:
        self.score += points


class GameState:
    """
    Holds all mutable game data.
    Replace the placeholders below with your actual game entities
    as described in DESIGN.md.

    Works for any number of players -- pass as many names as your
    game needs (one for a solo game, two, three, however many).
    """

    def __init__(self, player_names: Optional[list[str]] = None) -> None:
        if player_names is None:
            player_names = ["Player 1", "Player 2"]

        start_health: int = CONFIG["game"]["start_health"]
        self.players: list[Player] = [
            Player(name=name, health=start_health) for name in player_names
        ]

        self.turn: int = 1
        self.max_turns: int = CONFIG["game"]["max_turns"]
        self.current_player_index: int = 0
        self.phase: str = "setup"     # setup | play | resolve | game_over
        self.winner: Optional[int] = None  # index into self.players, or None

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    def advance_turn(self) -> None:
        """Move to the next player's turn, or end the game if max_turns reached."""
        self.current_player_index += 1
        if self.current_player_index >= len(self.players):
            self.current_player_index = 0
            self.turn += 1

        if self.turn > self.max_turns:
            self._end_game()

    def _end_game(self) -> None:
        self.phase = "game_over"
        top_score = max(p.score for p in self.players)
        leaders = [i for i, p in enumerate(self.players) if p.score == top_score]
        self.winner = leaders[0] if len(leaders) == 1 else None  # None on a tie

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def active_player(self) -> Player:
        return self.players[self.current_player_index]

    def is_over(self) -> bool:
        return self.phase == "game_over"
