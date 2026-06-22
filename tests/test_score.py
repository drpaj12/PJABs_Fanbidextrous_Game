# tests/test_score.py
from src.game.score import percent_complete, total_tiles_game, total_tiles_half


def test_tile_totals_scale_with_party_size():
    assert total_tiles_half(1, 1) == 12
    assert total_tiles_half(2, 1) == 16
    assert total_tiles_half(1, 3) == 36
    assert total_tiles_game(3) == (12 + 16) * 3   # 84


def test_percent_complete_clamps_and_rounds():
    assert percent_complete(0, 3) == 0
    assert percent_complete(42, 3) == 50          # 42 / 84
    assert percent_complete(100, 3) == 100        # clamped to total
