# tests/test_session.py
import random
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.prediction import Prediction
from src.game.session import GameSession, WindowResolution


def _hand() -> list[DraftedAthlete]:
    specs = [("a0", "ST", 5), ("a1", "CB", 3), ("a2", "CM", 4),
             ("a3", "GK", 2), ("a4", "WG", 3), ("a5", "DM", 3)]
    return [DraftedAthlete(athlete_id=i, name=i, broad_position="Midfielder",
            team="T", jersey=0, archetype=arch, stars=st) for i, arch, st in specs]


def test_exact_predictions_fill_success_meter_and_can_fire():
    pool = _hand()
    session = GameSession(slot=0, roster=Roster(_hand()), pool=pool,
                          rng=random.Random(7))
    # Three exact predictions = 3 * 2 = 6 success credit = threshold -> fires once.
    preds = [Prediction("corner", 3), Prediction("shot", 2)]
    actuals = {"corner": 3, "shot": 2, "goal": 0, "card": 0, "foul": 0}
    res: WindowResolution = session.resolve_window(
        window=1, predictions=preds, active_id="a0", use_power=False, actuals=actuals)
    # 2 exact preds -> 4 success credit, below threshold 6, no fire yet.
    assert session.success_meter.value == 4
    assert res.score_events == []


def test_big_miss_fills_concede_meter():
    session = GameSession(slot=0, roster=Roster(_hand()), pool=_hand(),
                          rng=random.Random(7))
    preds = [Prediction("corner", 0), Prediction("shot", 0)]
    actuals = {"corner": 9, "shot": 9, "goal": 0, "card": 0, "foul": 0}
    session.resolve_window(window=1, predictions=preds, active_id="a1",
                           use_power=False, actuals=actuals)
    # 2 big misses -> 2 * 2 = 4 concede credit.
    assert session.concede_meter.value == 4
