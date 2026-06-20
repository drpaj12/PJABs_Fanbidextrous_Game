# tests/test_live_play_screen_logic.py
"""Unit tests for the one piece of pure logic in the live play screen:
mapping newly-entered windows to (lock, resolve) actions."""
from src.ui.screens.live_play_screen import lock_and_resolve_plan


def test_kickoff_locks_w1_resolves_nothing() -> None:
    assert lock_and_resolve_plan([1], editing_start=1) == [(1, None)]


def test_boundary_locks_next_resolves_prev() -> None:
    assert lock_and_resolve_plan([2], editing_start=1) == [(2, 1)]


def test_focus_skip_chains_locks_and_resolves() -> None:
    assert lock_and_resolve_plan([2, 3, 4], editing_start=1) == [(2, 1), (3, 2), (4, 3)]


def test_mid_half_join_does_not_resolve_unowned_window() -> None:
    # joined editing window 6; entering 6 must not try to resolve window 5
    assert lock_and_resolve_plan([6], editing_start=6) == [(6, None)]
