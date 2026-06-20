# tests/test_ability_text.py
"""Pure ability describer: role blurbs, effect-line phrasing, number formatting, tagline.
No pygame. Athletes are built with explicit archetype/stars so effects are deterministic
(the create() classmethod derives them from a hash, which we deliberately bypass here)."""
from src.game.athlete import DraftedAthlete
from src.game import ability_text


def _ath(archetype: str, stars: int) -> DraftedAthlete:
    return DraftedAthlete(athlete_id="x", name="Test Player", broad_position="Attacker",
                          team="Testland", jersey=9, archetype=archetype, stars=stars)


def test_role_summary_is_archetype_blurb() -> None:
    s = ability_text.role_summary(_ath("ST", 5))
    assert s.startswith("Out-and-out striker")


def test_role_summary_falls_back_to_code_for_unknown() -> None:
    assert ability_text.role_summary(_ath("ZZ", 3)) == "ZZ"


def test_effect_lines_striker_5_star() -> None:
    # ST: this=conversion_add 0.20, next=concede_credit_add 1.5; conv_base 0.35.
    # 5*: mag = base*(0.6+0.2*5)=base*1.6; conv = 0.35+0.03*5 = 0.50.
    lines = ability_text.effect_lines(_ath("ST", 5))
    assert lines[0] == "This window: +32% shot conversion"   # 0.20*1.6 = 0.32
    assert lines[1] == "Next window: +2.4 concede risk"        # 1.5*1.6 = 2.4
    assert lines[2] == "Shot conversion: 50%"
    assert lines[3] == "Rating: *****"


def test_effect_lines_goalkeeper_includes_block_and_negative_credit() -> None:
    # GK: this=negate_concede_shot (no magnitude), next=success_credit_add -1.0.
    lines = ability_text.effect_lines(_ath("GK", 3))
    assert lines[0] == "This window: blocks a shot against you"
    assert lines[1] == "Next window: -1.2 success credit"      # -1.0*(0.6+0.2*3)=-1.2
    assert lines[2] == "Shot conversion: 19%"                   # 0.10+0.03*3 = 0.19


def test_effect_lines_playmaker_uses_multiplier_phrasing() -> None:
    # AM: this=success_credit_mult 2.0 -> x{mult}. 1*: 2.0*(0.6+0.2*1)=1.6.
    lines = ability_text.effect_lines(_ath("AM", 1))
    assert lines[0] == "This window: x1.6 success credit"


def test_card_tagline_is_this_window_phrase_without_prefix() -> None:
    assert ability_text.card_tagline(_ath("ST", 5)) == "+32% shot conversion"
    assert ability_text.card_tagline(_ath("GK", 3)) == "blocks a shot against you"


def test_all_strings_are_ascii() -> None:
    for arch in ("GK", "CB", "FB", "WB", "DM", "CM", "AM", "WG", "SS", "ST"):
        ath = _ath(arch, 4)
        blob = ability_text.role_summary(ath) + " ".join(ability_text.effect_lines(ath))
        blob += ability_text.card_tagline(ath)
        blob.encode("ascii")  # raises if any non-ASCII slipped in
