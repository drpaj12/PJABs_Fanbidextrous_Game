# tests/test_half_picker.py
"""Pure join-time half selection (golden rule: no pygame)."""
from src.game.half_picker import pick_half, HalfChoice

H = 45        # half_minutes
CUT = 22      # join_cutoff_minute (half-relative)


def call(status, elapsed):
    return pick_half(status, elapsed, half_minutes=H, join_cutoff_minute=CUT)


def test_prematch_plays_first_half():
    assert call("NS", 0) == HalfChoice(1, False)
    assert call("TBD", 0) == HalfChoice(1, False)


def test_first_half_before_cutoff_plays_first():
    assert call("1H", 0) == HalfChoice(1, False)
    assert call("1H", 21) == HalfChoice(1, False)


def test_first_half_at_or_after_cutoff_waits_for_second():
    assert call("1H", 22) == HalfChoice(2, True)
    assert call("1H", 40) == HalfChoice(2, True)


def test_halftime_waits_for_second():
    assert call("HT", 45) == HalfChoice(2, True)


def test_second_half_before_cutoff_plays_second():
    assert call("2H", 46) == HalfChoice(2, False)   # 46-45=1 < 22
    assert call("2H", 66) == HalfChoice(2, False)   # 66-45=21 < 22


def test_second_half_at_or_after_cutoff_has_no_half_left():
    assert call("2H", 67) == HalfChoice(None, False)  # 67-45=22 >= 22
    assert call("2H", 85) == HalfChoice(None, False)


def test_extra_time_and_breaks_have_no_half_left():
    assert call("ET", 95) == HalfChoice(None, False)
    assert call("BT", 91) == HalfChoice(None, False)
    assert call("P", 120) == HalfChoice(None, False)


def test_finished_has_no_half_left():
    for s in ("FT", "AET", "PEN", "ABD", "AWD", "WO", "CANC"):
        assert call(s, 90) == HalfChoice(None, False)


def test_unknown_status_defaults_to_no_half():
    assert call("???", 10) == HalfChoice(None, False)
