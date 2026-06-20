# tests/test_live_flow_lock.py
"""LiveFlow._on_lock bridges the live screen to the scoring engine: it resolves a window
against the live feed, advances the meters, appends any score codes, and returns the
WindowReport the screen renders inline.

This exercises the pure bridge (session + clock + feed), built directly on a LiveFlow whose
play screen is never constructed -- no pygame surface needed, though importing src.ui.flow
pulls pygame (installed). The two snapshots cover window 1's start (0') and end (5') minutes.
"""
import random

from src.game.live_feed import LiveFeed
from src.game.half_clock import HalfClock
from src.game.athlete import DraftedAthlete
from src.game.prediction import Prediction
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.window_report import WindowReport
from src.ui.flow import LiveFlow, _HALF_MIN, _WINDOW_MIN
from src.ui.sim import SimMode


class _FakeApp:
    """Records set_screen calls; never builds a real screen."""

    def __init__(self) -> None:
        self.screens: list = []
        self.global_handler = None
        self.overlay = None

    def set_screen(self, screen) -> None:
        self.screens.append(screen)


def _stats(corners: int, shots: int, fouls: int) -> dict:
    return {"response": [{"team": {"name": "Canada"}, "statistics": [
        {"type": "Corner Kicks", "value": corners},
        {"type": "Shots on Goal", "value": shots},
        {"type": "Fouls", "value": fouls},
    ]}]}


def _fixture(short: str, elapsed: int) -> dict:
    return {"response": [{
        "fixture": {"id": 1, "status": {"short": short, "elapsed": elapsed}},
        "teams": {"home": {"name": "Canada"}, "away": {"name": "X"}},
        "goals": {"home": 0, "away": 0}}]}


def _snap(elapsed: int, corners: int, shots: int, fouls: int) -> dict:
    return {"lineups": {"response": []}, "statistics": _stats(corners, shots, fouls),
            "fixture": _fixture("1H", elapsed)}


def _hand() -> list[DraftedAthlete]:
    rows = [("a0", "Striker"), ("a1", "Defender"), ("a2", "Midfielder"),
            ("a3", "Goalkeeper"), ("a4", "Attacker"), ("a5", "Midfielder")]
    return [DraftedAthlete.create(athlete_id=i, name=i, broad_position=p,
            team="Canada", jersey=k) for k, (i, p) in enumerate(rows, 1)]


def _flow(feed: LiveFeed) -> LiveFlow:
    pool = _hand()
    clock = HalfClock(_HALF_MIN, _WINDOW_MIN)
    flow = LiveFlow(_FakeApp(), feed, FeedClientStub(), fixture_id=1, pool=pool,
                    half=1, clock=clock, kickoff_epoch=0.0, sim=SimMode(False),
                    to_picker=lambda: None)
    flow.session = GameSession(slot=0, roster=Roster(pool), pool=pool,
                               rng=random.Random(7))
    return flow


class FeedClientStub:
    is_lead = True


def test_on_lock_returns_report_and_advances_engine() -> None:
    # Window 1 spans minutes 0..5. End-minus-start deltas: corners 3, shots 2, fouls 4.
    feed = LiveFeed()
    feed.record(_snap(0, 0, 0, 0))
    feed.record(_snap(5, 3, 2, 4))
    flow = _flow(feed)

    # Predict the corner delta exactly and shots exactly -> success credit accrues.
    preds = [Prediction("corner", 3), Prediction("shot", 2)]
    report = flow._on_lock(1, preds, "a0", False)

    assert isinstance(report, WindowReport)
    assert report.window == 1
    by_code = {r.code: r for r in report.results}
    assert by_code["corner"].actual == 3 and by_code["corner"].outcome == "exact"
    assert by_code["shot"].actual == 2 and by_code["shot"].outcome == "exact"

    # Two exact predictions -> 2 * 2 = 4 success credit on the meter (below threshold,
    # so no fire and no score codes appended).
    assert flow.session.success_meter.value == 4
    assert report.success_value == 4
    assert flow.score_codes == []


def test_on_lock_appends_score_code_when_meter_fires() -> None:
    # A big miss on both stats drives the concede meter to its threshold so it fires,
    # producing one "against" score event whose code is appended.
    feed = LiveFeed()
    feed.record(_snap(0, 0, 0, 0))
    feed.record(_snap(5, 9, 9, 9))   # corners/shots/fouls actually 9; we predicted 0
    flow = _flow(feed)

    preds = [Prediction("corner", 0), Prediction("shot", 0),
             Prediction("foul", 0)]
    report = flow._on_lock(1, preds, "a1", False)

    # Three big misses -> 3 * 2 = 6 concede credit = threshold -> fires, meter resets to 0.
    assert report.concede_fired is True
    assert len(flow.score_codes) == 1
    assert flow.score_codes[0].split(":")[2] == "against"


def test_window_actuals_for_et_uses_last_known_minute() -> None:
    # ET window (index 10) has no clock end; actuals span start..last_known_minute.
    feed = LiveFeed()
    feed.record(_snap(45, 9, 9, 17))
    feed.record(_snap(48, 11, 10, 19))   # stoppage; last known minute = 48
    flow = _flow(feed)
    et = HalfClock(_HALF_MIN, _WINDOW_MIN).extra_time_window

    actuals = flow._window_actuals_for(et)
    # 48' minus 45': corners 2, shots 1, fouls 2.
    assert actuals["corner"] == 2
    assert actuals["shot"] == 1
    assert actuals["foul"] == 2
