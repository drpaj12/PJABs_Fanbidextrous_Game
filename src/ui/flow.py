# src/ui/flow.py
"""Full single-device flow controller.

Splash -> Room -> Draft -> Play loop [Predict -> Cinematic] -> Final.
Builds the draft pool from a feed's recorded lineups. SIM mode (hotkeys + help popup)
is threaded into every screen. The engine is untouched; meter before/after values are
captured around resolve_window to drive the cinematic.
"""
import random
from typing import TYPE_CHECKING
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed
from src.game.athlete import DraftedAthlete
from src.game.prediction import Prediction
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.game.cinematic import CinematicScript, build_cinematic_script
from src.ui.sim import SimMode
from src.ui.widgets import LogList
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.ui.screens.cinematic_screen import CinematicScreen
from src.ui.screens.status_screens import FinalScreen
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_STAT_LABELS = {s["code"]: s["label"] for s in _STATS_MENU["stats"]}
_THRESH = CONFIG["meter"]["success_threshold"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_RNG_SEED = CONFIG["game"]["rng_seed"]


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


def _pool_from_feed(feed: MockFeed) -> list[DraftedAthlete]:
    return [DraftedAthlete.create(athlete_id=r["athlete_id"], name=r["name"],
            broad_position=r["broad_position"], team=r["team"], jersey=int(r["jersey"]))
            for r in feed.lineups()]


class Flow:
    """Owns the screen sequence and shared state for one single-device match."""

    def __init__(self, app: "App", feed: MockFeed, pool: list[DraftedAthlete],
                 sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.sim = sim
        self.log = self._new_log()
        self.session: GameSession | None = None
        self.score_codes: list[str] = []
        self.minute = 0
        self.window = 1
        self._pending_script: CinematicScript | None = None
        self.app.global_handler = self.sim.handle_global
        self.app.overlay = self.sim.draw_overlay

    def _new_log(self) -> "LogList":
        import pygame
        sw = self.app.screen.get_width()
        m = LAYOUT.i("screen_margin", 20)
        return LogList(pygame.Rect(m, LAYOUT.i("play_log_top", 100),
                                   sw - 2 * m, LAYOUT.i("play_log_h", 360)))

    # -- flow steps --
    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._after_splash, self.sim))

    def _after_splash(self) -> None:
        self.app.set_screen(RoomScreen(self.app, self._after_room, self.sim))

    def _after_room(self, code: str) -> None:
        self.app.set_screen(DraftScreen(self.app, self.pool, self._after_draft,
                                        self.sim, title="Draft your six"))

    def _after_draft(self, selected: list[str]) -> None:
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        self._play_window()

    def _play_window(self) -> None:
        available = self.session.roster.available()
        self.app.set_screen(PlayScreen(self.app, available, self._after_predict,
                                       self.log, self.window, self.sim))

    def _after_predict(self, preds: list[Prediction], active_id: str,
                       use_power: bool) -> None:
        end_min = self.minute + _WINDOW_MIN
        a = self.feed.snapshot_at(self.minute)
        b = self.feed.snapshot_at(end_min)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        actuals = actuals_from_raw(raw, _STATS_MENU)

        s_before = self.session.success_meter.value
        c_before = self.session.concede_meter.value
        res = self.session.resolve_window(window=self.window, predictions=preds,
                                           active_id=active_id, use_power=use_power,
                                           actuals=actuals)
        s_after = self.session.success_meter.value
        c_after = self.session.concede_meter.value
        for ev in res.score_events:
            self.score_codes.append(ev.to_code())

        script = build_cinematic_script(
            predictions=preds, actuals=actuals,
            success_before=s_before, success_after=s_after, success_fired=res.success_fired,
            concede_before=c_before, concede_after=c_after, concede_fired=res.concede_fired,
            threshold=_THRESH, score_events=res.score_events, stat_labels=_STAT_LABELS)

        self.minute = end_min
        self.app.set_screen(CinematicScreen(self.app, script, self._after_cinematic, self.sim))
        self._pending_script = script

    def _after_cinematic(self) -> None:
        team, opp = aggregate(self.score_codes)
        s = self._pending_script
        self.log.add(f"W{self.window}: +{s.team_delta} for / +{s.opp_delta} against "
                     f"(you {team}-{opp} opp)")
        if s.team_delta > 0:
            self.log.add(f"GOAL window {self.window}!")
        self.window += 1
        if self.feed.match_status_at(self.minute) == "finished":
            self.app.set_screen(FinalScreen(self.app, team, opp, None))
        else:
            self._play_window()


def start_simulation(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    Flow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()


def start(app: "App", sim_mode: bool = False) -> None:
    Flow(app, MockFeed(_demo_script()), _demo_pool(), SimMode(sim_mode)).start()
