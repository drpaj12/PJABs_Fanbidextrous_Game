# tests/test_diag_log.py
"""Pure diagnostic line buffer for the SIM harness (no pygame, golden rule)."""
from src.game.diag_log import DiagLog, _stamp


def test_disabled_is_a_no_op():
    d = DiagLog(enabled=False, actor="drpaj")
    d.add(20, "QUERY", "get_feed")
    assert d.all_lines() == []
    assert d.drain() == []


def test_local_line_format_is_ascii_and_tagged():
    d = DiagLog(enabled=True, actor="drpaj")
    d.add(20, "QUERY", "get_feed(fixture=FRA-CRO) -> lkm=20")
    line = d.all_lines()[0]
    assert line == "[drpaj] t=+20:00 min=20' QUERY get_feed(fixture=FRA-CRO) -> lkm=20"
    assert line.isascii()


def test_explicit_seconds_from_kickoff_negative_pregame():
    d = DiagLog(enabled=True, actor="drpaj")
    d.add(0, "KICKOFF", "set offset=-5", seconds_from_kickoff=-300)
    assert d.all_lines()[0] == "[drpaj] t=-05:00 min=0' KICKOFF set offset=-5"


def test_peer_line_uses_peer_tag():
    d = DiagLog(enabled=True, actor="drpaj")
    d.add_peer("ally", 25, "OBSERVED", "bundle W2 in blob")
    assert d.all_lines()[0] == "[ally] t=+25:00 min=25' OBSERVED bundle W2 in blob"


def test_drain_returns_only_new_lines():
    d = DiagLog(enabled=True, actor="drpaj")
    d.add(10, "A")
    first = d.drain()
    assert first == ["[drpaj] t=+10:00 min=10' A"]
    d.add(11, "B")
    assert d.drain() == ["[drpaj] t=+11:00 min=11' B"]
    assert d.drain() == []                      # nothing new


def test_combined_timeline_interleaves_actors():
    d = DiagLog(enabled=True, actor="drpaj")
    d.add(20, "SHARE", "bundle W1")
    d.add_peer("ally", 20, "JOINED", "")
    d.add(25, "SHARE", "bundle W2")
    tags = [ln.split("]")[0] + "]" for ln in d.all_lines()]
    assert tags == ["[drpaj]", "[ally]", "[drpaj]"]


def test_stamp_rounds_seconds():
    assert _stamp(0) == "+00:00"
    assert _stamp(90) == "+01:30"
    assert _stamp(-61) == "-01:01"
