# src/ui/demo_flow.py
"""Single-device demo: MockFeed + one GameSession, walking draft -> predict -> watch -> final."""
import random
from src.game.mock_feed import MockFeed
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.predict_screen import PredictScreen
from src.ui.screens.status_screens import WatchScreen, RevealScreen, FinalScreen


def _demo_pool() -> list[DraftedAthlete]:
    rows = [("sccr-1", "A. Davies", "Defender"), ("sccr-2", "J. David", "Attacker"),
            ("sccr-3", "S. Eustaquio", "Midfielder"), ("sccr-4", "M. Crepeau", "Goalkeeper"),
            ("sccr-5", "T. Buchanan", "Defender"), ("sccr-6", "C. Larin", "Attacker"),
            ("sccr-7", "I. Kone", "Midfielder"), ("sccr-8", "A. Hernandez", "Defender"),
            ("sccr-9", "L. Brym", "Attacker"), ("sccr-10", "M. Kone", "Midfielder")]
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="Canada", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _demo_script() -> dict:
    return {
        "status_by_minute": [(0, "live"), (15, "finished")],
        "snapshots": [
            {"minute": 0,  "stats": {"corner_kicks": 0, "shots_on_goal": 0, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 5,  "stats": {"corner_kicks": 3, "shots_on_goal": 2, "goalkeeper_saves": 2, "goals": 0, "cards": 1}},
            {"minute": 10, "stats": {"corner_kicks": 6, "shots_on_goal": 5, "goalkeeper_saves": 3, "goals": 1, "cards": 1}},
            {"minute": 15, "stats": {"corner_kicks": 8, "shots_on_goal": 7, "goalkeeper_saves": 5, "goals": 2, "cards": 2}},
        ],
    }


def start(app) -> None:
    pool = _demo_pool()
    feed = MockFeed(_demo_script())
    state = {"window": 1, "minute": 0}

    def after_draft(selected: list[str]) -> None:
        hand = [a for a in pool if a.athlete_id in selected]
        session = GameSession(slot=0, roster=Roster(hand), pool=pool, rng=random.Random(99))
        score_codes: list[str] = []
        _run_window(app, feed, pool, session, state, score_codes)

    app.set_screen(DraftScreen(app, pool, after_draft))


def _stat_deltas(feed: MockFeed, start_min: int, end_min: int) -> dict[str, int]:
    a = feed.snapshot_at(start_min)
    b = feed.snapshot_at(end_min)
    keys = set(a.stats) | set(b.stats)
    return {k.replace("corner_kicks", "corner").replace("shots_on_goal", "shot")
             .replace("goalkeeper_saves", "save").replace("goals", "goal")
             .replace("cards", "card"): b.delta(a, k) for k in keys}


def _run_window(app, feed, pool, session, state, score_codes) -> None:
    minute = state["minute"]
    available = session.roster.available()

    def after_predict(preds, active_id, use_power) -> None:
        end_min = minute + 5
        actuals = _stat_deltas(feed, minute, end_min)
        res = session.resolve_window(window=state["window"], predictions=preds,
                                     active_id=active_id, use_power=use_power, actuals=actuals)
        for ev in res.score_events:
            score_codes.append(ev.to_code())
        team, opp = aggregate(score_codes)
        lines = [f"Window {state['window']} resolved.",
                 f"Attack meter: {session.success_meter.value}",
                 f"Danger meter: {session.concede_meter.value}",
                 f"Score: you {team} - {opp} opp"]
        for ev in res.score_events:
            lines.append(("GOAL!" if ev.scored and ev.side == "for" else
                          "CONCEDED!" if ev.scored else "shot missed"))

        def cont() -> None:
            state["minute"] = end_min
            state["window"] += 1
            if feed.match_status_at(end_min) == "finished":
                team2, opp2 = aggregate(score_codes)
                app.set_screen(FinalScreen(app, team2, opp2, None))
            else:
                _run_window(app, feed, pool, session, state, score_codes)

        app.set_screen(RevealScreen(app, lines, cont))

    app.set_screen(PredictScreen(app, available, after_predict))
