# tests/test_athlete.py
from src.game.athlete import DraftedAthlete, derive_archetype, derive_stars


def test_archetype_is_deterministic_and_in_bucket():
    a1 = derive_archetype("sccr-501", "Defender")
    a2 = derive_archetype("sccr-501", "Defender")
    assert a1 == a2
    assert a1 in ("CB", "FB", "WB")


def test_stars_deterministic_in_range():
    s1 = derive_stars("sccr-501")
    s2 = derive_stars("sccr-501")
    assert s1 == s2
    assert 1 <= s1 <= 5


def test_drafted_athlete_carries_derived_fields():
    ath = DraftedAthlete.create(athlete_id="sccr-7", name="A. Davies",
                                broad_position="Defender", team="CAN", jersey=19)
    assert ath.archetype in ("CB", "FB", "WB")
    assert 1 <= ath.stars <= 5
