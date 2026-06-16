# tests/test_roster.py
import pytest
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster


def _hand(n: int) -> list[DraftedAthlete]:
    return [DraftedAthlete(athlete_id=f"a{i}", name=f"P{i}",
            broad_position="Midfielder", team="T", jersey=i,
            archetype="CM", stars=3) for i in range(n)]


def test_available_excludes_used_until_cycle_resets():
    r = Roster(_hand(6))
    assert len(r.available()) == 6
    r.use("a0")
    assert "a0" not in [a.athlete_id for a in r.available()]
    for i in range(1, 6):
        r.use(f"a{i}")
    # all 6 used -> cycle resets, all available again
    assert len(r.available()) == 6


def test_use_unavailable_raises():
    r = Roster(_hand(6))
    r.use("a0")
    with pytest.raises(ValueError):
        r.use("a0")
