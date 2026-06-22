# src/game/live_resume.py
"""Serialize / restore a live half so a player can close the tab and come back in exactly
where they were: same +/- guesses, same selected player, same score, same meters.

Pure data only -- ZERO pygame and zero UI imports -- so the whole save/restore contract is
unit-testable. The UI layer (flow + LivePlayScreen) gathers the live objects into the plain
values this module stores, and rebuilds them from a parsed blob on re-entry.

The blob is keyed per (user, fixture, half) so the two halves resume independently and one
player's resume can never read another's. It carries only this player's own game state -- no
tokens, no opponent data -- and lives in localStorage (web) / a JSON file (desktop).

The random state is captured verbatim (random.Random.getstate()) so deferred shot resolution
after a resume produces the identical outcome it would have had the tab never closed.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Optional

VERSION = 1


def resume_key(username: str, fixture_id: int, half: int) -> str:
    """localStorage / file key for one player's in-progress half."""
    return f"resume_v{VERSION}:{username}:{fixture_id}:{half}"


def rng_to_jsonable(state: tuple) -> list:
    """random.Random.getstate() -> JSON-safe list. State is (version, internal_tuple, gauss);
    the middle is a tuple of ints which JSON cannot hold as a tuple, so it becomes a list."""
    return [state[0], list(state[1]), state[2]]


def rng_from_jsonable(data: list) -> tuple:
    """Inverse of rng_to_jsonable -- rebuild the exact tuple random.setstate() requires."""
    return (data[0], tuple(data[1]), data[2])


@dataclass
class LiveResumeState:
    """Everything needed to rebuild a half mid-flight. `editor` is the LivePlayScreen's own
    plain-dict snapshot (dials, locked windows, high-water mark); the rest is session state."""
    fixture_id: int
    half: int
    selected_ids: list[str]          # the drafted six (rebuilds roster + identifies the hand)
    used_ids: list[str]              # roster rotation already spent this cycle
    success_value: int
    concede_value: int
    pending_next: dict               # the carried-over power effect for the next window
    rng_state: list                  # JSON-safe random.Random.getstate()
    score_codes: list[str]           # the player's accumulated score events
    editor: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": VERSION,
            "fixture_id": self.fixture_id,
            "half": self.half,
            "selected_ids": list(self.selected_ids),
            "used_ids": list(self.used_ids),
            "success_value": self.success_value,
            "concede_value": self.concede_value,
            "pending_next": dict(self.pending_next),
            "rng_state": self.rng_state,
            "score_codes": list(self.score_codes),
            "editor": self.editor,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def parse(raw: Optional[str]) -> Optional[LiveResumeState]:
    """Parse a stored blob back into a LiveResumeState, or None when there is nothing valid to
    resume (missing, empty/cleared, malformed, or a version we do not understand). Defensive by
    design: a bad blob must NEVER crash the live flow -- it just means "start fresh"."""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("version") != VERSION:
        return None
    try:
        return LiveResumeState(
            fixture_id=int(d["fixture_id"]),
            half=int(d["half"]),
            selected_ids=[str(x) for x in d["selected_ids"]],
            used_ids=[str(x) for x in d["used_ids"]],
            success_value=int(d["success_value"]),
            concede_value=int(d["concede_value"]),
            pending_next=dict(d["pending_next"]),
            rng_state=d["rng_state"],
            score_codes=[str(x) for x in d["score_codes"]],
            editor=dict(d.get("editor") or {}),
        )
    except (KeyError, TypeError, ValueError):
        return None


def can_restore(state: LiveResumeState, half: int, roster_ids: set[str]) -> bool:
    """True only when this blob is safe to apply right now: it is for THIS half and every
    drafted player it references still exists in the current pool (lineups rebuilt from the
    feed). If lineups have not loaded yet, roster_ids is empty and we decline -- start fresh."""
    if state.half != half:
        return False
    if not state.selected_ids:
        return False
    return all(aid in roster_ids for aid in state.selected_ids)
