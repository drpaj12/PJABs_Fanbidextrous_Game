"""Tests for the pure live-resume serialization contract (src/game/live_resume.py)."""
import json
import random

from src.game.live_resume import (LiveResumeState, VERSION, can_restore, parse,
                                   resume_key, rng_from_jsonable, rng_to_jsonable)


def _state(**over) -> LiveResumeState:
    base = dict(
        fixture_id=1539007, half=1,
        selected_ids=["a", "b", "c", "d", "e", "f"],
        used_ids=["a", "b"],
        success_value=3, concede_value=1,
        pending_next={"kind": "none", "value": 0.0},
        rng_state=rng_to_jsonable(random.Random(99).getstate()),
        score_codes=["0:2:for:1", "0:3:against:0"],
        editor={"edit_window": 4, "lines": {"shots": 2}},
    )
    base.update(over)
    return LiveResumeState(**base)


def test_resume_key_is_per_user_fixture_half():
    assert resume_key("drpaj", 1539007, 1) == f"resume_v{VERSION}:drpaj:1539007:1"
    assert resume_key("drpaj", 1539007, 1) != resume_key("drpaj", 1539007, 2)
    assert resume_key("drpaj", 1539007, 1) != resume_key("other", 1539007, 1)


def test_round_trip_preserves_all_fields():
    s = _state()
    back = parse(s.to_json())
    assert back is not None
    assert back.fixture_id == s.fixture_id
    assert back.half == s.half
    assert back.selected_ids == s.selected_ids
    assert back.used_ids == s.used_ids
    assert back.success_value == s.success_value
    assert back.concede_value == s.concede_value
    assert back.pending_next == s.pending_next
    assert back.score_codes == s.score_codes
    assert back.editor == s.editor


def test_rng_state_round_trips_to_identical_stream():
    rng = random.Random(99)
    [rng.random() for _ in range(5)]            # advance off the seed
    saved = rng_to_jsonable(rng.getstate())
    expected = [rng.random() for _ in range(3)]  # the stream that should resume

    # A fresh RNG restored from the saved state must produce the SAME next numbers.
    restored = random.Random()
    restored.setstate(rng_from_jsonable(json.loads(json.dumps(saved))))
    assert [restored.random() for _ in range(3)] == expected


def test_parse_rejects_empty_and_garbage():
    assert parse(None) is None
    assert parse("") is None
    assert parse("not json {") is None
    assert parse(json.dumps([1, 2, 3])) is None


def test_parse_rejects_wrong_version():
    d = _state().to_dict()
    d["version"] = VERSION + 1
    assert parse(json.dumps(d)) is None


def test_parse_rejects_missing_field():
    d = _state().to_dict()
    del d["success_value"]
    assert parse(json.dumps(d)) is None


def test_can_restore_requires_matching_half():
    s = _state(half=1)
    ids = set(s.selected_ids)
    assert can_restore(s, 1, ids) is True
    assert can_restore(s, 2, ids) is False


def test_can_restore_requires_all_players_present():
    s = _state()
    full = set(s.selected_ids)
    assert can_restore(s, 1, full) is True
    # Lineups not loaded / a player missing -> decline and start fresh.
    assert can_restore(s, 1, set()) is False
    assert can_restore(s, 1, full - {"a"}) is False
