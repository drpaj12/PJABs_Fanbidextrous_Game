# src/game/feed_cache_policy.py
"""Pure policy for the client-side warm cache (no I/O here -- src/sync/local_store does that).

On restart the client loads the last relay snapshot it saved so the lineups/score/clock show
instantly and no API call is spent re-learning them. These helpers own the storage key, the
blob format, and the rule for whether a restart still needs a fresh poll."""
import json
from typing import Optional


def cache_key(username: str, fixture_id: int) -> str:
    """Per-user, per-fixture key. Same username (case/space-insensitive) + same fixture maps
    to the same slot, so a restart reuses the cache."""
    return f"predictor:{(username or '').strip().lower()}:{int(fixture_id)}"


def make_blob(snapshot: dict, now: float) -> dict:
    """Wrap a relay snapshot with the wall-clock time it was stored."""
    return {"snapshot": snapshot, "cached_at": float(now)}


def serialize(blob: dict) -> str:
    """Encode a blob for storage. The blob must be JSON-serializable (it is, by
    construction -- make_blob wraps a relay snapshot, which is decoded JSON)."""
    return json.dumps(blob)


def deserialize(text: Optional[str]) -> Optional[dict]:
    """Parse a stored blob; None on missing/corrupt data (never raises)."""
    if not text:
        return None
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def should_poll_on_start(blob: Optional[dict], now: float, poll_seconds: float) -> bool:
    """True if the client should poll immediately on startup. False only when a cached blob
    is younger than one poll interval (warm start, no API call needed yet)."""
    if not blob or "cached_at" not in blob:
        return True
    return (now - float(blob["cached_at"])) >= poll_seconds
