"""
test_game_state.py -- tests for src/game/game_state.py

Run with:  python -m pytest tests/

Rules:
- No pygame imports in tests (game logic must work without a display)
- Test the things that DESIGN.md guarantees -- if the doc says "player
  with most points wins," there must be a test for that
- Add a test every time you add a new game rule
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game.game_state import GameState, Player
from src.game.rules import apply_action, check_winner


class TestPlayer:
    def test_starts_with_configured_health(self):
        p = Player(name="Alice", health=10)
        assert p.health == 10

    def test_is_alive_when_health_positive(self):
        p = Player(name="Alice", health=5)
        assert p.is_alive() is True

    def test_is_dead_at_zero_health(self):
        p = Player(name="Alice", health=0)
        assert p.is_alive() is False

    def test_take_damage_reduces_health(self):
        p = Player(name="Alice", health=10)
        p.take_damage(3)
        assert p.health == 7

    def test_take_damage_cannot_go_below_zero(self):
        p = Player(name="Alice", health=2)
        p.take_damage(10)
        assert p.health == 0

    def test_add_score(self):
        p = Player(name="Alice", health=10, score=0)
        p.add_score(5)
        assert p.score == 5


class TestGameState:
    def test_initial_state(self):
        state = GameState()
        assert state.turn == 1
        assert state.current_player_index == 0
        assert state.phase == "setup"
        assert state.winner is None
        assert not state.is_over()

    def test_defaults_to_two_players(self):
        state = GameState()
        assert len(state.players) == 2

    def test_supports_any_number_of_players(self):
        state = GameState(player_names=["Alice", "Bob", "Cara"])
        assert len(state.players) == 3

    def test_active_player_is_first_player_at_start(self):
        state = GameState()
        assert state.active_player().name == "Player 1"

    def test_advance_turn_moves_to_next_player(self):
        state = GameState()
        state.advance_turn()
        assert state.current_player_index == 1

    def test_advance_turn_wraps_and_increments_turn(self):
        state = GameState()
        state.advance_turn()  # player 0 -> player 1
        state.advance_turn()  # player 1 -> player 0, turn becomes 2
        assert state.turn == 2
        assert state.current_player_index == 0

    def test_game_ends_after_max_turns(self):
        state = GameState()
        max_t = state.max_turns
        for _ in range(max_t * len(state.players)):
            if state.is_over():
                break
            state.advance_turn()
        assert state.is_over()


class TestRules:
    def test_apply_action_rejects_wrong_player(self):
        state = GameState()
        action = {"type": "place", "target": 1, "entity_index": 0}
        result = apply_action(state, player_index=1, action=action)
        assert result is False

    def test_apply_place_action_scores_points(self):
        state = GameState()
        action = {"type": "place", "target": 1, "entity_index": 0}
        apply_action(state, player_index=0, action=action)
        assert state.players[0].score > 0

    def test_apply_action_returns_false_when_game_over(self):
        state = GameState()
        state.phase = "game_over"
        action = {"type": "place", "target": 1, "entity_index": 0}
        result = apply_action(state, player_index=0, action=action)
        assert result is False

    def test_check_winner_detects_last_player_standing(self):
        state = GameState()
        state.players[0].health = 0
        check_winner(state)
        assert state.winner == 1
        assert state.is_over()

    def test_check_winner_works_with_more_than_two_players(self):
        state = GameState(player_names=["Alice", "Bob", "Cara"])
        state.players[0].health = 0
        state.players[1].health = 0
        check_winner(state)
        assert state.winner == 2
        assert state.is_over()
