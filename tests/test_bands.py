# tests/test_bands.py
from src.game.bands import Band, grade_progress, window_color


def test_exact_close_near():
    assert grade_progress(3, 3).key == "exact" and grade_progress(3, 3).step == 3
    assert grade_progress(3, 4).key == "close" and grade_progress(3, 4).step == 2
    assert grade_progress(3, 5).key == "near" and grade_progress(3, 5).step == 1


def test_off_and_big_miss():
    assert grade_progress(3, 7).key == "off" and grade_progress(3, 7).step == 0   # diff 4
    b = grade_progress(0, 7)                                                       # diff 7
    assert b.key == "big_miss" and b.step == -1 and b.is_big_miss is True


def test_window_color_thresholds():
    assert window_color(8, False) == "green"
    assert window_color(5, False) == "orange"
    assert window_color(2, False) == "red"
    assert window_color(10, True) == "red"   # any big miss forces red
