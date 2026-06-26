# src/game/staleness.py
"""Pure staleness rules for the shared party blob (peer co-op).

A party_N.json file on the relay outlives a single match -- nothing on the server deletes it
between games, so a client that joins party 3 today can read state frozen from a game played
on it yesterday. Two independent signals tell a client the blob it just read is leftover and
must not be trusted or replayed:

  1. fixture mismatch -- the api-lead is about to start a DIFFERENT fixture than the one frozen
     in the blob (blob.fixture_id is set and differs from the chosen fixture).
  2. age -- more than `stale_minutes` have elapsed since the blob's kickoff, measured by the
     relay's own clock (server_time), so even the same fixture is long finished.

Both are pure functions of values the client already holds (the blob fields + the relay's
server_time). Zero pygame, zero I/O -- fully unit-testable, per the golden rule."""
from datetime import datetime, timezone
from typing import Optional


def _parse_iso_epoch(kickoff_iso: str) -> Optional[float]:
    """Parse an ISO-8601 kickoff string into a UTC epoch (seconds). Returns None for an empty
    or malformed string -- a blob that never recorded a kickoff has no age to measure."""
    if not kickoff_iso:
        return None
    try:
        dt = datetime.fromisoformat(kickoff_iso)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def fixture_mismatch(blob_fixture_id: int, chosen_fixture_id: int) -> bool:
    """True when the blob holds a real fixture that differs from the one we are about to start.
    fixture_id 0 means 'never set' (still in lobby) -> never a mismatch."""
    return int(blob_fixture_id) != 0 and int(blob_fixture_id) != int(chosen_fixture_id)


def kickoff_expired(kickoff_iso: str, server_time: float, stale_minutes: int) -> bool:
    """True when more than `stale_minutes` have elapsed since kickoff by the relay clock. A
    blob with no recorded kickoff (epoch None) is NOT expired by age."""
    epoch = _parse_iso_epoch(kickoff_iso)
    if epoch is None:
        return False
    return (float(server_time) - epoch) > int(stale_minutes) * 60


def is_blob_stale(blob_fixture_id: int, kickoff_iso: str, server_time: Optional[float],
                  stale_minutes: int, chosen_fixture_id: Optional[int] = None) -> bool:
    """Combined gate. The blob is stale when EITHER its age has expired OR (when a fixture is
    being chosen) the chosen fixture differs from the blob's.

    chosen_fixture_id is None for a follower -- it does not choose a game, so age is the only
    signal. server_time None (a relay that did not report its clock) disables the age signal."""
    if server_time is not None and kickoff_expired(kickoff_iso, server_time, stale_minutes):
        return True
    if chosen_fixture_id is not None and fixture_mismatch(blob_fixture_id, chosen_fixture_id):
        return True
    return False
