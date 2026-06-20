from src.game.half_clock import HalfClock
from src.game.match_clock import MatchClock

# 45-min half, 5-min windows -> 9 regular windows, ET window = 10.
CLOCK = HalfClock(45, 5)
K = 1_000_000.0  # arbitrary kickoff epoch


def mc():
    return MatchClock(kickoff_epoch=K, clock=CLOCK)


def test_before_kickoff_is_minute_zero_window_zero_editing_one():
    m = mc()
    assert m.current_minute(K - 120) == 0
    assert m.playing_window(K - 120) == 0
    assert m.editing_window(K - 120) == 1


def test_at_kickoff_window_one_plays_and_you_edit_two():
    m = mc()
    assert m.current_minute(K) == 0
    assert m.playing_window(K) == 1
    assert m.editing_window(K) == 2


def test_minute_and_windows_advance():
    m = mc()
    assert m.current_minute(K + 5 * 60) == 5
    assert m.playing_window(K + 5 * 60) == 2
    assert m.editing_window(K + 5 * 60) == 3


def test_mid_half_join():
    m = mc()
    assert m.current_minute(K + 23 * 60) == 23
    assert m.playing_window(K + 23 * 60) == 5   # 20-25' window
    assert m.editing_window(K + 23 * 60) == 6


def test_extra_time_window_caps():
    m = mc()
    assert m.playing_window(K + 45 * 60) == 10   # ET window
    assert m.editing_window(K + 45 * 60) == 10   # nothing beyond ET
    assert m.playing_window(K + 60 * 60) == 10   # stays at ET past 45'


def test_windows_entered_at_kickoff():
    m = mc()
    assert m.windows_entered(K - 1, K + 1) == [1]


def test_windows_entered_at_a_boundary():
    m = mc()
    assert m.windows_entered(K + 4 * 60, K + 5 * 60) == [2]


def test_windows_entered_handles_a_focus_loss_skip():
    m = mc()
    # tab backgrounded from 4' (window 1) to 16' (window 4): catch up 2,3,4
    assert m.windows_entered(K + 4 * 60, K + 16 * 60) == [2, 3, 4]


def test_windows_entered_empty_when_no_boundary():
    m = mc()
    assert m.windows_entered(K + 60, K + 90) == []


def test_windows_entered_crossing_into_extra_time():
    # the game-meaningful 9 -> 10 step: leaving the last regular window (40-45')
    # and entering the Extra-Time window at 45'.
    m = mc()
    assert m.windows_entered(K + 44 * 60, K + 45 * 60) == [10]
