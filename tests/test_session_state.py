from src.sync.session_state import SessionState


def test_window_for_minute_uses_window_seconds():
    st = SessionState(room=0, token="t", seed=123, slot=0)
    # window_seconds=300 -> 5-min windows; minute 0-4 -> window 1, 5-9 -> window 2
    assert st.window_for_minute(0) == 1
    assert st.window_for_minute(4) == 1
    assert st.window_for_minute(5) == 2


def test_record_and_aggregate_score_events():
    st = SessionState(room=0, token="t", seed=123, slot=0)
    st.add_score_event("0:1:for:1")
    st.add_score_event("1:1:against:1")
    team, opp = st.shared_score()
    assert team == 1 and opp == 1
