# src/ui/flow.py
"""Full single-device flow controller.

Splash -> Room -> Pre-game -> Draft -> Play loop [Predict -> Cinematic] -> Half Time.
The half is `regular_windows` five-minute windows (minutes 0-45) plus one Extra-Time
window that resolves over all first-half stoppage, discovered by polling the feed for
a half-time status. The engine is untouched; meter before/after values are captured
around resolve_window to drive the cinematic.
"""
import random
from typing import TYPE_CHECKING, Optional
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed
from src.game.live_feed import LiveFeed
from src.game.live_schedule import LivePlan, live_plan
from src.game.athlete import DraftedAthlete
from src.game.prediction import Prediction
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.game.cinematic import build_cinematic_script
from src.game.half_clock import HalfClock
from src.game.window_report import WindowReport, build_window_report
from src.sync.feed_client import FeedClient
from src.ui.sim import SimMode
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
from src.ui.screens.pregame_screen import PregameScreen
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.ui.screens.cinematic_screen import CinematicScreen
from src.ui.screens.status_screens import FinalScreen
from src.ui.screens.live_wait_screen import LiveWaitScreen
from src.ui.screens.fixture_select_screen import FixtureSelectScreen
from src.ui.screens.launcher_screen import LauncherScreen
from src.ui.screens.username_screen import UsernameScreen
from src.utils.constants import CONFIG, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_STAT_LABELS = {s["code"]: s["label"] for s in _STATS_MENU["stats"]}
_THRESH = CONFIG["meter"]["success_threshold"]
_THRESH_C = CONFIG["meter"]["concede_threshold"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_HALF_MIN = CONFIG["game"]["half_minutes"]
_HALF_LABEL = CONFIG["game"]["half_label"]
_HALFTIME_LABEL = CONFIG["game"]["halftime_label"]
_ET_LABEL = CONFIG["game"]["extra_time_label"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_POLL_SECONDS = CONFIG["feed"]["poll_seconds"]
_RNG_SEED = CONFIG["game"]["rng_seed"]
_PREGAME = CONFIG["pregame"]
_LIVE = CONFIG["live"]
_LAUNCHER = CONFIG["launcher"]
_LEAD_NAME = CONFIG["client"]["lead_username"]


def _demo_pool() -> list[DraftedAthlete]:
    rows = [("sccr-1", "A. Davies", "Defender"), ("sccr-2", "J. David", "Attacker"),
            ("sccr-3", "S. Eustaquio", "Midfielder"), ("sccr-4", "M. Crepeau", "Goalkeeper"),
            ("sccr-5", "T. Buchanan", "Defender"), ("sccr-6", "C. Larin", "Attacker"),
            ("sccr-7", "I. Kone", "Midfielder"), ("sccr-8", "A. Hernandez", "Defender"),
            ("sccr-9", "L. Brym", "Attacker"), ("sccr-10", "M. Kone", "Midfielder")]
    return [DraftedAthlete.create(athlete_id=i, name=n, broad_position=p,
            team="Canada", jersey=k) for k, (i, n, p) in enumerate(rows, 1)]


def _demo_script() -> dict:
    """A full first half: cumulative stats every 5 minutes 0-45, plus 3 minutes of
    stoppage (45 -> 48), with a halftime status at minute 48."""
    return {
        "status_by_minute": [(0, "live"), (48, "halftime")],
        "snapshots": [
            {"minute": 0,  "stats": {"corner_kicks": 0,  "shots_on_goal": 0, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 5,  "stats": {"corner_kicks": 1,  "shots_on_goal": 1, "goalkeeper_saves": 0, "goals": 0, "cards": 0}},
            {"minute": 10, "stats": {"corner_kicks": 2,  "shots_on_goal": 2, "goalkeeper_saves": 1, "goals": 0, "cards": 0}},
            {"minute": 15, "stats": {"corner_kicks": 3,  "shots_on_goal": 3, "goalkeeper_saves": 1, "goals": 0, "cards": 1}},
            {"minute": 20, "stats": {"corner_kicks": 4,  "shots_on_goal": 4, "goalkeeper_saves": 2, "goals": 1, "cards": 1}},
            {"minute": 25, "stats": {"corner_kicks": 5,  "shots_on_goal": 5, "goalkeeper_saves": 2, "goals": 1, "cards": 1}},
            {"minute": 30, "stats": {"corner_kicks": 6,  "shots_on_goal": 6, "goalkeeper_saves": 3, "goals": 1, "cards": 1}},
            {"minute": 35, "stats": {"corner_kicks": 7,  "shots_on_goal": 7, "goalkeeper_saves": 3, "goals": 1, "cards": 2}},
            {"minute": 40, "stats": {"corner_kicks": 8,  "shots_on_goal": 8, "goalkeeper_saves": 4, "goals": 2, "cards": 2}},
            {"minute": 45, "stats": {"corner_kicks": 9,  "shots_on_goal": 9, "goalkeeper_saves": 4, "goals": 2, "cards": 2}},
            {"minute": 48, "stats": {"corner_kicks": 10, "shots_on_goal": 9, "goalkeeper_saves": 5, "goals": 2, "cards": 2}},
        ],
    }


def _pool_from_feed(feed: MockFeed) -> list[DraftedAthlete]:
    return [DraftedAthlete.create(athlete_id=r["athlete_id"], name=r["name"],
            broad_position=r["broad_position"], team=r["team"], jersey=int(r["jersey"]))
            for r in feed.lineups()]


class Flow:
    """Owns the screen sequence and shared state for one single-device half."""

    def __init__(self, app: "App", feed: MockFeed, pool: list[DraftedAthlete],
                 sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.sim = sim
        self.clock = HalfClock(_HALF_MIN, _WINDOW_MIN)
        self.last_report: Optional[WindowReport] = None
        self.session: Optional[GameSession] = None
        self.score_codes: list[str] = []
        self.window = 1
        self.app.global_handler = self.sim.handle_global
        self.app.overlay = self.sim.draw_overlay

    # -- flow steps --
    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._after_splash, self.sim))

    def _after_splash(self) -> None:
        self.app.set_screen(RoomScreen(self.app, self._after_room, self.sim))

    def _after_room(self, code: str) -> None:
        self.app.set_screen(PregameScreen(self.app, self._fixture(),
                                           self._after_pregame, self.sim))

    def _after_pregame(self) -> None:
        self.app.set_screen(DraftScreen(self.app, self.pool, self._after_draft,
                                        self.sim, title="Draft your six"))

    def _after_draft(self, selected: list[str]) -> None:
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        self._play_window()

    def _fixture(self) -> dict:
        meta = getattr(self.feed, "meta", {})
        return {
            "home": meta.get("home_team", _PREGAME["default_home_team"]),
            "away": meta.get("away_team", _PREGAME["default_away_team"]),
            "competition": meta.get("competition", _PREGAME["default_competition"]),
            "label": _HALF_LABEL,
        }

    def _play_window(self) -> None:
        available = self.session.roster.available()
        phase = _ET_LABEL if self.clock.is_extra_time(self.window) else None
        self.app.set_screen(PlayScreen(self.app, available, self._after_predict,
                                       self.window, self.sim, self.last_report,
                                       phase_label=phase))

    def _poll_half_end(self, start: int) -> int:
        """Emulate live polling: step forward from `start`, asking the feed its status
        each minute, and stop at the first minute the half is reported over (bounded by
        the feed's last known minute so a feed that never reports halftime terminates)."""
        last = self.feed.last_known_minute()
        m = start
        while m < last and not HalfClock.is_half_over(
                self.feed.match_status_at(m), _HALFTIME_STATUS):
            m += 1
        return m

    def _window_actuals(self) -> dict[str, int]:
        start = self.clock.window_start(self.window)
        if self.clock.is_extra_time(self.window):
            end = self._poll_half_end(start)
        else:
            end = self.clock.window_end(self.window)
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _after_predict(self, preds: list[Prediction], active_id: str,
                       use_power: bool) -> None:
        actuals = self._window_actuals()

        s_before = self.session.success_meter.value
        c_before = self.session.concede_meter.value
        res = self.session.resolve_window(window=self.window, predictions=preds,
                                           active_id=active_id, use_power=use_power,
                                           actuals=actuals)
        s_after = self.session.success_meter.value
        c_after = self.session.concede_meter.value
        for ev in res.score_events:
            self.score_codes.append(ev.to_code())

        self.last_report = build_window_report(
            window=self.window, predictions=preds, actuals=actuals,
            stat_labels=_STAT_LABELS, success_value=s_after, concede_value=c_after,
            success_threshold=_THRESH, concede_threshold=_THRESH_C,
            success_fired=res.success_fired, concede_fired=res.concede_fired,
            success_shot=res.success_shot, concede_shot=res.concede_shot)

        script = build_cinematic_script(
            predictions=preds, actuals=actuals,
            success_before=s_before, success_after=s_after, success_fired=res.success_fired,
            concede_before=c_before, concede_after=c_after, concede_fired=res.concede_fired,
            threshold=_THRESH, score_events=res.score_events, stat_labels=_STAT_LABELS)

        self.app.set_screen(CinematicScreen(self.app, script, self._after_cinematic, self.sim))

    def _after_cinematic(self) -> None:
        team, opp = aggregate(self.score_codes)
        if self.clock.is_extra_time(self.window):
            self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                            title=_HALFTIME_LABEL))
        else:
            self.window += 1
            self._play_window()


class LiveFlow(Flow):
    """A live half: drives windows from a live_plan's remaining-window list, and waits on
    the wall clock (polling the relay) between locking predictions and resolving each
    window. Reuses Flow's splash -> room -> pre-game -> draft and the resolve/cinematic
    machinery; only the window iteration and the "play it out, then resolve" gap differ."""

    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, pool: list[DraftedAthlete], plan: LivePlan,
                 sim: SimMode) -> None:
        super().__init__(app, feed, pool, sim)
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self._scored = plan.scored_windows
        self._idx = 0

    def _fixture(self) -> dict:
        return {
            "home": self.feed.home_team() or _PREGAME["default_home_team"],
            "away": self.feed.away_team() or _PREGAME["default_away_team"],
            "competition": _LIVE["competition_label"],
            "label": _HALF_LABEL,
        }

    def _after_draft(self, selected: list[str]) -> None:
        self.window = self._scored[self._idx]
        super()._after_draft(selected)

    def _window_actuals(self) -> dict[str, int]:
        # As Flow, but a live Extra-Time window resolves over everything polled so far
        # (the live status would otherwise short-circuit the parent's minute-by-minute scan).
        start = self.clock.window_start(self.window)
        if self.clock.is_extra_time(self.window):
            end = self.feed.last_known_minute()
        else:
            end = self.clock.window_end(self.window)
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _after_predict(self, preds: list[Prediction], active_id: str,
                       use_power: bool) -> None:
        # Lock the picks, then wait out the window on the wall clock before resolving.
        target = None if self.clock.is_extra_time(self.window) \
            else self.clock.window_end(self.window)

        def resolve() -> None:
            Flow._after_predict(self, preds, active_id, use_power)

        self.app.set_screen(LiveWaitScreen(
            self.app, self.feed, self.feed_client, self.fixture_id,
            target_minute=target, on_ready=resolve, poll_seconds=_POLL_SECONDS,
            sim=self.sim))

    def _after_cinematic(self) -> None:
        team, opp = aggregate(self.score_codes)
        self._idx += 1
        if self._idx >= len(self._scored):
            self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                            title=_HALFTIME_LABEL))
        else:
            self.window = self._scored[self._idx]
            self._play_window()


def start_live(app: "App", fixture_id: int, sim_mode: bool = False,
               is_lead: bool = False) -> None:
    """Live single-player half. Park on a waiting screen until the API publishes the
    starting XI, then size the half from the live match clock and run the draft + windows.
    Only the lead client (is_lead) spends API-Football quota; followers read the cache."""
    feed = LiveFeed()
    feed_client = FeedClient(CONFIG["relay"]["base_url"],
                             feed_path=CONFIG["relay"]["feed_path"], is_lead=is_lead)
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay

    def begin() -> None:
        clock = HalfClock(_HALF_MIN, _WINDOW_MIN)
        plan = live_plan(feed.current_minute(), feed.match_status(), clock)
        if not plan.scored_windows:
            app.set_screen(FinalScreen(app, 0, 0, "First half already over",
                                       title=_HALFTIME_LABEL))
            return
        pool = _pool_from_feed(feed)
        LiveFlow(app, feed, feed_client, fixture_id, pool, plan, sim).start()

    app.set_screen(LiveWaitScreen(app, feed, feed_client, fixture_id,
                                  target_minute=None, on_ready=begin,
                                  poll_seconds=_POLL_SECONDS, sim=sim,
                                  wait_for_lineups=True))


def start_live_select(app: "App", sim_mode: bool = False,
                      is_lead: bool = False) -> None:
    """Show the live-match picker (config live.fixtures), then play the chosen one live.
    This is the web/no-argument entry point for match day."""
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    fixtures = _LIVE.get("fixtures") or []

    def picked(fixture_id: int) -> None:
        start_live(app, fixture_id, sim_mode=sim_mode, is_lead=is_lead)

    app.set_screen(FixtureSelectScreen(app, fixtures, picked, sim))


def start_app(app: "App", sim_mode: bool = False) -> None:
    """Top web entry: ask for a username, then show the mode menu. A username matching
    config.client.lead_username (case-insensitive) becomes the lead client that polls
    the live scores; everyone else free-rides on the website cache."""
    def submitted(username: str) -> None:
        is_lead = username.strip().lower() == _LEAD_NAME.lower()
        start_launcher(app, sim_mode=sim_mode, is_lead=is_lead)

    app.set_screen(UsernameScreen(app, submitted))


def start_launcher(app: "App", sim_mode: bool = False, is_lead: bool = False) -> None:
    """Web entry: choose 'Live match' (real fixtures + relay) or 'Test game' (an offline
    recorded match, no API/no waiting) so the full flow can be tried without a live game."""
    def go_live() -> None:
        start_live_select(app, sim_mode=sim_mode, is_lead=is_lead)

    def go_sim() -> None:
        start_simulation(app, _LAUNCHER["test_sim"], sim_mode=True)

    options = [
        (_LAUNCHER["live_label"], go_live),
        (_LAUNCHER["sim_label"], go_sim),
    ]
    app.set_screen(LauncherScreen(app, options))


def start_simulation(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    Flow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()


def start(app: "App", sim_mode: bool = False) -> None:
    Flow(app, MockFeed(_demo_script()), _demo_pool(), SimMode(sim_mode)).start()
