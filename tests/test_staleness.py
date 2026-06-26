"""Pure staleness rules for the shared party blob: a different chosen fixture, or a game whose
kickoff is older than the configured max lifetime, marks the blob leftover and not to be
replayed. These cover both signals independently and combined, plus the empty/malformed and
None-server_time edge cases the live join path relies on."""
from src.game.staleness import (fixture_mismatch, is_blob_stale, kickoff_expired,
                                _parse_iso_epoch)

_KICK = "2026-06-20T17:00:00+00:00"
_KICK_EPOCH = 1781974800.0   # 2026-06-20 17:00 UTC


def test_parse_iso_epoch_roundtrip():
    assert _parse_iso_epoch(_KICK) == _KICK_EPOCH


def test_parse_iso_epoch_naive_treated_as_utc():
    assert _parse_iso_epoch("2026-06-20T17:00:00") == _KICK_EPOCH


def test_parse_iso_epoch_empty_or_malformed_is_none():
    assert _parse_iso_epoch("") is None
    assert _parse_iso_epoch("not-a-date") is None


def test_fixture_mismatch_only_when_blob_has_a_different_real_fixture():
    assert fixture_mismatch(1539007, 1489393) is True     # different real game
    assert fixture_mismatch(1539007, 1539007) is False    # same game
    assert fixture_mismatch(0, 1539007) is False          # blob still in lobby (id 0)


def test_kickoff_expired_after_threshold():
    # 100 minutes after kickoff is NOT yet expired (boundary); 101 minutes is.
    assert kickoff_expired(_KICK, _KICK_EPOCH + 100 * 60, 100) is False
    assert kickoff_expired(_KICK, _KICK_EPOCH + 101 * 60, 100) is True


def test_kickoff_expired_no_kickoff_is_never_expired():
    assert kickoff_expired("", _KICK_EPOCH + 9999 * 60, 100) is False


def test_is_blob_stale_age_signal():
    # Same fixture, but the game is long over -> stale.
    assert is_blob_stale(1539007, _KICK, _KICK_EPOCH + 200 * 60, 100,
                         chosen_fixture_id=1539007) is True


def test_is_blob_stale_fixture_signal():
    # Fresh kickoff, but a different fixture is being started -> stale.
    assert is_blob_stale(1539007, _KICK, _KICK_EPOCH + 5 * 60, 100,
                         chosen_fixture_id=1489393) is True


def test_is_blob_stale_fresh_same_fixture_is_not_stale():
    assert is_blob_stale(1539007, _KICK, _KICK_EPOCH + 5 * 60, 100,
                         chosen_fixture_id=1539007) is False


def test_is_blob_stale_lobby_blob_is_never_stale():
    # A blob still in lobby (fixture 0, no kickoff) is never stale, even for a chosen fixture.
    assert is_blob_stale(0, "", _KICK_EPOCH, 100, chosen_fixture_id=1539007) is False


def test_is_blob_stale_follower_uses_age_only():
    # Follower (chosen_fixture_id None) ignores the fixture signal; only age can mark it stale.
    assert is_blob_stale(1539007, _KICK, _KICK_EPOCH + 5 * 60, 100) is False
    assert is_blob_stale(1539007, _KICK, _KICK_EPOCH + 200 * 60, 100) is True


def test_is_blob_stale_none_server_time_disables_age():
    # A relay that did not report its clock cannot expire a blob by age.
    assert is_blob_stale(1539007, _KICK, None, 100, chosen_fixture_id=1539007) is False
