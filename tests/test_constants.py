# tests/test_constants.py
from src.utils.constants import CONFIG, load_data


def test_config_has_game_section():
    assert CONFIG["game"]["roster_size"] == 6
    assert CONFIG["game"]["window_seconds"] == 900


def test_load_data_reads_powers():
    powers = load_data(CONFIG["assets"]["powers_file"])
    assert "archetypes" in powers
    assert powers["archetypes"]["ST"]["conversion_base"] == 0.35
