from src.game.kickoff import (
    seconds_to_kickoff, kickoff_phase, format_countdown,
    PHASE_TOO_EARLY, PHASE_SOON, PHASE_ACTIVE,
)

# 2026-06-20 18:00:00 UTC
_KICK = "2026-06-20T18:00:00+00:00"
_KICK_EPOCH = 1781978400  # datetime(2026,6,20,18,tzinfo=utc).timestamp()


def test_seconds_to_kickoff_future_and_past():
    assert seconds_to_kickoff(_KICK, _KICK_EPOCH - 90) == 90
    assert seconds_to_kickoff(_KICK, _KICK_EPOCH + 120) == -120


def test_seconds_to_kickoff_handles_zulu_and_naive():
    assert seconds_to_kickoff("2026-06-20T18:00:00Z", _KICK_EPOCH) == 0
    assert seconds_to_kickoff("2026-06-20T18:00:00", _KICK_EPOCH) == 0  # naive -> UTC


def test_seconds_to_kickoff_missing_or_bad():
    assert seconds_to_kickoff(None, 0) is None
    assert seconds_to_kickoff("", 0) is None
    assert seconds_to_kickoff("not-a-date", 0) is None


def test_phase_too_early_then_soon_then_active():
    warn, start = 3600, 900  # 60 min, 15 min
    assert kickoff_phase(5400, "scheduled", warn, start) == PHASE_TOO_EARLY  # 90 min out
    assert kickoff_phase(1800, "scheduled", warn, start) == PHASE_SOON       # 30 min out
    assert kickoff_phase(300, "scheduled", warn, start) == PHASE_ACTIVE      # 5 min out


def test_phase_active_when_match_under_way_or_unknown():
    warn, start = 3600, 900
    assert kickoff_phase(9999, "live", warn, start) == PHASE_ACTIVE       # already live
    assert kickoff_phase(9999, "halftime", warn, start) == PHASE_ACTIVE
    assert kickoff_phase(None, "scheduled", warn, start) == PHASE_ACTIVE  # no kickoff time


def test_format_countdown():
    assert format_countdown(90) == "01:30"
    assert format_countdown(5400) == "1:30:00"
    assert format_countdown(-10) == "00:00"
