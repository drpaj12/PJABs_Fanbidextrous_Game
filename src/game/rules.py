"""
Rules -- win conditions, scoring, and turn validation.

Keep this module focused on WHAT IS LEGAL and WHAT SCORES POINTS.
No pygame, no rendering, no side effects beyond modifying GameState.
"""

from src.game.game_state import GameState
from src.utils.constants import CONFIG


def apply_action(state: GameState, player_index: int, action: dict) -> bool:
    """
    Validate and apply one player action to the game state.

    Returns True if the action was legal and applied, False otherwise.

    action dict shape (fill in for your game):
        { "type": "place", "target": 2, "entity_index": 0 }
    """
    if state.is_over():
        return False
    if state.current_player_index != player_index:
        return False

    action_type: str = action.get("type", "")

    if action_type == "place":
        return _handle_place(state, player_index, action)

    return False


def _handle_place(state: GameState, player_index: int, action: dict) -> bool:
    """
    Handle a 'place' action. Replace with your real placement logic.
    This is a stub -- describe what placement means in DESIGN.md
    and the AI agent will implement it from there.
    """
    points_per_action: int = CONFIG["game"]["points_per_action"]
    state.active_player().add_score(points_per_action)
    state.advance_turn()
    return True


def check_winner(state: GameState) -> None:
    """
    Check all win/lose conditions and update state.winner if the game is over.
    Called after every action. Extend with your actual conditions from DESIGN.md.

    Example below: last player standing wins. Works for any number of
    players -- replace with your real win condition from DESIGN.md.
    """
    if len(state.players) < 2:
        return

    alive = [i for i, p in enumerate(state.players) if p.is_alive()]
    if len(alive) <= 1:
        state.phase = "game_over"
        state.winner = alive[0] if alive else None
