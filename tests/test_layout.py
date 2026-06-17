# tests/test_layout.py
"""Layout helper: named keys with defaults, no pygame."""
from src.utils.constants import LAYOUT


def test_known_key_returns_config_value():
    # splash_title_size exists in config/layout_config.json
    assert LAYOUT.param("splash_title_size", 0) >= 24


def test_unknown_key_returns_default():
    assert LAYOUT.param("does_not_exist_xyz", 17) == 17


def test_int_helper_casts():
    assert isinstance(LAYOUT.i("draft_card_h", 60), int)
