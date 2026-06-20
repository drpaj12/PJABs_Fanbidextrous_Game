# tests/test_live_play_screen_logic.py
"""Unit tests for the pure logic in the live play screen: mapping newly-entered windows to
(lock, resolve) actions, and gating resolution on feed data availability."""
from src.game.half_clock import HalfClock
from src.ui.screens.live_play_screen import (lock_and_resolve_plan, windows_ready,
                                             windows_to_enter)

# 45-min half, 5-min windows -> window_end(1)=5, (2)=10, (3)=15, ...
CLOCK = HalfClock(45, 5)


def test_kickoff_locks_w1_resolves_nothing() -> None:
    assert lock_and_resolve_plan([1], editing_start=1) == [(1, None)]


def test_boundary_locks_next_resolves_prev() -> None:
    assert lock_and_resolve_plan([2], editing_start=1) == [(2, 1)]


def test_focus_skip_chains_locks_and_resolves() -> None:
    assert lock_and_resolve_plan([2, 3, 4], editing_start=1) == [(2, 1), (3, 2), (4, 3)]


def test_mid_half_join_does_not_resolve_unowned_window() -> None:
    # joined editing window 6; entering 6 must not try to resolve window 5
    assert lock_and_resolve_plan([6], editing_start=6) == [(6, None)]


def test_windows_ready_only_when_feed_covers_window_end() -> None:
    pending = {1, 2, 3}  # ends 5, 10, 15
    assert windows_ready(pending, last_known_minute=5, clock=CLOCK) == [1]
    assert windows_ready(pending, last_known_minute=12, clock=CLOCK) == [1, 2]
    assert windows_ready(pending, last_known_minute=15, clock=CLOCK) == [1, 2, 3]


def test_windows_ready_holds_back_slept_through_windows() -> None:
    # tab backgrounded from 12' to the catch-up poll: nothing resolves while the feed is
    # stale at minute 12, then all queued windows clear once the fresh poll lands at 31.
    pending = {4, 5, 6}  # ends 20, 25, 30
    assert windows_ready(pending, last_known_minute=12, clock=CLOCK) == []
    assert windows_ready(pending, last_known_minute=31, clock=CLOCK) == [4, 5, 6]


def test_windows_ready_empty_pending() -> None:
    assert windows_ready(set(), last_known_minute=99, clock=CLOCK) == []


def test_windows_to_enter_forward_progress() -> None:
    assert windows_to_enter(max_entered=0, playing_window=1) == [1]
    assert windows_to_enter(max_entered=3, playing_window=4) == [4]


def test_windows_to_enter_catches_up_skipped_windows() -> None:
    # backgrounded across several boundaries: catch up all of them at once
    assert windows_to_enter(max_entered=2, playing_window=5) == [3, 4, 5]


def test_windows_to_enter_backward_realign_yields_nothing() -> None:
    # a backward clock correction (playing_window < high-water) must not re-enter
    assert windows_to_enter(max_entered=6, playing_window=4) == []
    assert windows_to_enter(max_entered=4, playing_window=4) == []
