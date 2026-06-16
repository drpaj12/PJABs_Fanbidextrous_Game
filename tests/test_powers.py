# tests/test_powers.py
from src.game.athlete import DraftedAthlete
from src.game.powers import (
    scaled_magnitude, conversion_for, this_window_effect, next_window_effect,
)


def _striker() -> DraftedAthlete:
    # find an id that hashes to ST is brittle; build directly:
    return DraftedAthlete(athlete_id="x", name="S", broad_position="Attacker",
                          team="T", jersey=9, archetype="ST", stars=5)


def test_scaled_magnitude_uses_star_formula():
    # base 1.0, 5 stars -> 0.6 + 0.2*5 = 1.6
    assert abs(scaled_magnitude(1.0, 5) - 1.6) < 1e-9
    # 1 star -> 0.6 + 0.2 = 0.8
    assert abs(scaled_magnitude(1.0, 1) - 0.8) < 1e-9


def test_conversion_includes_star_bonus():
    ath = _striker()
    # ST base 0.35 + conv_per_star(0.03)*5 = 0.50
    assert abs(conversion_for(ath) - 0.50) < 1e-9


def test_effects_return_kind_and_scaled_value():
    ath = _striker()
    tw = this_window_effect(ath)
    assert tw["kind"] == "conversion_add"
    # base 0.20 scaled by 5-star magnitude 1.6 -> 0.32
    assert abs(tw["value"] - 0.32) < 1e-9
    nw = next_window_effect(ath)
    assert nw["kind"] == "concede_credit_add"
