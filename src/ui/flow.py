# src/ui/flow.py
"""Full single-device flow controller.

Splash -> Room -> Pre-game -> Draft -> Play loop [Predict -> Cinematic] -> Half Time.
The half is `regular_windows` five-minute windows (minutes 0-45) plus one Extra-Time
window that resolves over all first-half stoppage, discovered by polling the feed for
a half-time status. The engine is untouched; meter before/after values are captured
around resolve_window to drive the cinematic.
"""
import asyncio
import random
import time
from typing import TYPE_CHECKING, Callable, Optional
from src.game.mock_feed import MockFeed
from src.game.replay_feed import ReplayFeed
from src.game.live_feed import LiveFeed
from src.game.live_schedule import live_plan
from src.game.athlete import DraftedAthlete
from src.game.prediction import Prediction
from src.game.roster import Roster
from src.game.session import GameSession
from src.game.scoring import aggregate
from src.game.cinematic import build_cinematic_script
from src.game.half_clock import HalfClock, window_data_ready
from src.game.match_clock import MatchClock
from src.game.half_picker import pick_half
from src.game.kickoff import seconds_to_kickoff
from src.game.window_report import WindowReport, build_window_report
from src.game import feed_cache_policy as cachep
from src.game import live_resume
from src.sync.feed_client import FeedClient
from src.sync.highscore_client import HighscoreClient
from src.sync.local_store import LocalStore
from src.ui.sim import SimMode
from src.ui.screens.splash import SplashScreen
from src.ui.screens.room import RoomScreen
from src.ui.screens.pregame_screen import PregameScreen
from src.ui.screens.draft_screen import DraftScreen
from src.ui.screens.play_screen import PlayScreen
from src.ui.screens.cinematic_screen import CinematicScreen
from src.ui.screens.status_screens import (FinalScreen, RevealScreen, DungeonFinalScreen,
                                            DungeonHalfScreen)
from src.ui.screens.shop_screen import ShopScreen
from src.ui.screens.dungeon_play_screen import DungeonPlayScreen
from src.game.crawl import CrawlSession
from src.game.window_resolver import WindowResult
from src.game.score import total_tiles_game
from src.ui.screens.live_wait_screen import LiveWaitScreen
from src.ui.screens.live_resolve_screen import LiveResolveScreen
from src.ui.screens.live_play_screen import LivePlayScreen
from src.ui.screens.fixture_select_screen import FixtureSelectScreen
from src.ui.screens.sim_game_select_screen import SimGameSelectScreen
from src.game.simulations import list_simulations
from src.game.schedule import load_schedule
from src.ui.screens.launcher_screen import LauncherScreen
from src.ui.screens.username_screen import UsernameScreen
from src.utils.constants import CONFIG, ROOT, load_data
from src.ui.screens.party_screen import PartyScreen
from src.ui.screens.party_lobby_screen import PartyLobbyScreen
from src.ui.screens.party_play_screen import PartyPlayScreen
from src.sync.relay_client import RelayClient
from src.sync.party_coordinator import PartyCoordinator

if TYPE_CHECKING:
    from src.ui.app import App

_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])
_STAT_LABELS = {s["code"]: s["label"] for s in _STATS_MENU["stats"]}
_THRESH = CONFIG["meter"]["success_threshold"]
_THRESH_C = CONFIG["meter"]["concede_threshold"]
_WINDOW_MIN = CONFIG["game"]["window_seconds"] // 60
_HALF_MIN = CONFIG["game"]["half_minutes"]
_HALF_LABEL = CONFIG["game"]["half_label"]
_SECOND_HALF_LABEL = CONFIG["game"]["second_half_label"]
_HALFTIME_LABEL = CONFIG["game"]["halftime_label"]
_FULLTIME_LABEL = CONFIG["game"]["fulltime_label"]
_ET_LABEL = CONFIG["game"]["extra_time_label"]
_HALFTIME_STATUS = CONFIG["feed"]["halftime_status"]
_FINISHED_STATUS = "finished"
_POLL_SECONDS = CONFIG["feed"]["poll_seconds"]
_RESOLVE_POLL_SECONDS = CONFIG["feed"]["live_resolve_poll_seconds"]
_RNG_SEED = CONFIG["game"]["rng_seed"]
_RECAP_LOG_LINES = int(CONFIG["dungeon"]["recap_log_lines"])
_PREGAME = CONFIG["pregame"]
_LIVE = CONFIG["live"]
_LAUNCHER = CONFIG["launcher"]
_LEAD_NAME = CONFIG["client"]["lead_username"]
_JOIN_CUTOFF = CONFIG["live"]["join_cutoff_minute"]
_RESYNC_THRESHOLD = CONFIG["live"]["resync_threshold_seconds"]
_WINDOWS_PER_HALF = CONFIG["game"]["windows_per_half"]
_DUNGEON_PARTY_SIZE = CONFIG["game"]["dungeon_party_size"]
_SIMS_DIR = _LAUNCHER["simulations_dir"]


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
            {"minute": 0,  "stats": {"corner_kicks": 0,  "shots_on_goal": 0, "fouls": 0,  "goals": 0, "cards": 0}},
            {"minute": 5,  "stats": {"corner_kicks": 1,  "shots_on_goal": 1, "fouls": 2,  "goals": 0, "cards": 0}},
            {"minute": 10, "stats": {"corner_kicks": 2,  "shots_on_goal": 2, "fouls": 4,  "goals": 0, "cards": 0}},
            {"minute": 15, "stats": {"corner_kicks": 3,  "shots_on_goal": 3, "fouls": 5,  "goals": 0, "cards": 1}},
            {"minute": 20, "stats": {"corner_kicks": 4,  "shots_on_goal": 4, "fouls": 7,  "goals": 1, "cards": 1}},
            {"minute": 25, "stats": {"corner_kicks": 5,  "shots_on_goal": 5, "fouls": 9,  "goals": 1, "cards": 1}},
            {"minute": 30, "stats": {"corner_kicks": 6,  "shots_on_goal": 6, "fouls": 11, "goals": 1, "cards": 1}},
            {"minute": 35, "stats": {"corner_kicks": 7,  "shots_on_goal": 7, "fouls": 13, "goals": 1, "cards": 2}},
            {"minute": 40, "stats": {"corner_kicks": 8,  "shots_on_goal": 8, "fouls": 15, "goals": 2, "cards": 2}},
            {"minute": 45, "stats": {"corner_kicks": 9,  "shots_on_goal": 9, "fouls": 17, "goals": 2, "cards": 2}},
            {"minute": 48, "stats": {"corner_kicks": 10, "shots_on_goal": 9, "fouls": 19, "goals": 2, "cards": 2}},
        ],
    }


def _pool_from_feed(feed: MockFeed) -> list[DraftedAthlete]:
    return _pool_from_rows(feed.lineups())


def _pool_from_rows(rows: list[dict]) -> list[DraftedAthlete]:
    """Build the draft pool from lineup-row dicts (athlete_id/name/broad_position/team/jersey).
    Used by both the leader (rows from the live feed) and a follower (the same rows read back
    from the shared party blob), so both clients derive an identical pool."""
    return [DraftedAthlete.create(athlete_id=r["athlete_id"], name=r["name"],
            broad_position=r["broad_position"], team=r["team"], jersey=int(r["jersey"]))
            for r in rows]


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
    """A live half hosted by the single unified LivePlayScreen. The screen runs a wall-clock
    MatchClock for the whole half and calls back into the flow to resolve each window as its
    boundary passes (`_on_lock`) and to reach the FinalScreen when the half ends
    (`_to_final`). Reuses Flow's splash -> room -> pre-game -> draft; only the play phase
    differs (one always-running screen instead of the predict/wait/cinematic cycle)."""

    def __init__(self, app: "App", feed: LiveFeed, feed_client: FeedClient,
                 fixture_id: int, pool: list[DraftedAthlete], half: int,
                 clock: HalfClock, kickoff_epoch: float, sim: SimMode,
                 to_picker: Callable[[], None], on_snapshot=None,
                 username: str = "", game_label: str = "",
                 highscore_client: Optional[HighscoreClient] = None,
                 resume_blob: Optional["live_resume.LiveResumeState"] = None,
                 on_resume_save: Optional[Callable[[str], None]] = None,
                 on_resume_clear: Optional[Callable[[], None]] = None) -> None:
        super().__init__(app, feed, pool, sim)
        self.feed_client = feed_client
        self.fixture_id = fixture_id
        self.half = half
        self.clock = clock                       # half-aware (start_minute set by caller)
        self.kickoff_epoch = kickoff_epoch
        self.to_picker = to_picker
        self.half_label = _SECOND_HALF_LABEL if half == 2 else _HALF_LABEL
        self.on_snapshot = on_snapshot
        self.username = username
        self.game_label = game_label             # e.g. "Netherlands v Sweden"
        self.highscore_client = highscore_client
        self.resume_blob = resume_blob           # set when re-entering a half in progress
        self.on_resume_save = on_resume_save
        self.on_resume_clear = on_resume_clear
        self.selected_ids: list[str] = []        # the drafted six, for the resume blob
        self.live_screen: Optional[LivePlayScreen] = None

    def _fixture(self) -> dict:
        return {
            "home": self.feed.home_team() or _PREGAME["default_home_team"],
            "away": self.feed.away_team() or _PREGAME["default_away_team"],
            "competition": _LIVE["competition_label"],
            "label": self.half_label,
        }

    def start(self) -> None:
        """Resume jumps straight back into the live screen (no splash/room/pregame/draft);
        a fresh half runs the normal Flow sequence ending in _after_draft."""
        if self.resume_blob is not None:
            self._resume_play()
        else:
            super().start()

    def _after_draft(self, selected: list[str]) -> None:
        # Build the session from the drafted hand (as Flow does), then hand the whole half
        # to the unified live screen instead of stepping window-by-window.
        self.selected_ids = list(selected)
        hand = [a for a in self.pool if a.athlete_id in selected]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        match_clock = MatchClock(self.kickoff_epoch, self.clock)
        editing_start = match_clock.editing_window(time.time())
        self._show_live_screen(match_clock, editing_start, restore=None)

    def _resume_play(self) -> None:
        """Rebuild the half from a saved blob: the same drafted hand, meters, score, RNG and
        rotation state, then the screen's editor + locked windows. Falls back to a fresh draft
        if anything is off (lineups not loaded, player vanished) so resume can never dead-end."""
        blob = self.resume_blob
        roster_ids = {a.athlete_id for a in self.pool}
        if blob is None or not live_resume.can_restore(blob, self.half, roster_ids):
            self.resume_blob = None
            super().start()
            return
        self.selected_ids = list(blob.selected_ids)
        hand = [a for a in self.pool if a.athlete_id in blob.selected_ids]
        self.session = GameSession(slot=0, roster=Roster(hand), pool=self.pool,
                                   rng=random.Random(_RNG_SEED))
        self.session.success_meter.value = blob.success_value
        self.session.concede_meter.value = blob.concede_value
        self.session._pending_next = dict(blob.pending_next)
        try:
            self.session.rng.setstate(live_resume.rng_from_jsonable(blob.rng_state))
        except (ValueError, TypeError, IndexError):
            pass   # keep the freshly seeded RNG if the saved state is unusable
        self.score_codes = list(blob.score_codes)
        for aid in blob.used_ids:
            if aid in roster_ids:
                self.session.roster.use(aid)
        match_clock = MatchClock(self.kickoff_epoch, self.clock)
        editing_start = int(blob.editor.get("editing_start",
                                            match_clock.editing_window(time.time())))
        self._show_live_screen(match_clock, editing_start, restore=blob.editor)

    def _show_live_screen(self, match_clock: MatchClock, editing_start: int,
                          restore: Optional[dict]) -> None:
        screen = LivePlayScreen(
            app=self.app, feed=self.feed, feed_client=self.feed_client,
            match_clock=match_clock, fixture_id=self.fixture_id,
            editing_window_start=editing_start, on_lock=self._on_lock,
            on_finished=self._to_final, poll_seconds=_POLL_SECONDS,
            roster=self.session.roster, half_label=self.half_label,
            resync_threshold_seconds=_RESYNC_THRESHOLD,
            sim=self.sim, on_snapshot=self.on_snapshot,
            score_fn=lambda: aggregate(self.score_codes),
            on_change=self._save_resume)
        if restore:
            screen.restore_editor(restore)
        self.live_screen = screen
        self.app.set_screen(screen)

    def _save_resume(self) -> None:
        """Persist a resume point. Fully guarded -- a serialization or storage failure must
        never interrupt play."""
        if (self.on_resume_save is None or self.session is None
                or self.live_screen is None):
            return
        try:
            blob = live_resume.LiveResumeState(
                fixture_id=self.fixture_id, half=self.half,
                selected_ids=list(self.selected_ids),
                used_ids=self.session.roster.used_ids(),
                success_value=self.session.success_meter.value,
                concede_value=self.session.concede_meter.value,
                pending_next=dict(self.session._pending_next),
                rng_state=live_resume.rng_to_jsonable(self.session.rng.getstate()),
                score_codes=list(self.score_codes),
                editor=self.live_screen.snapshot_editor())
            self.on_resume_save(blob.to_json())
        except Exception:
            pass

    def _window_actuals_for(self, window: int) -> dict[str, int]:
        """Actuals (per-stat deltas) for one window. A live Extra-Time window resolves over
        everything polled so far (its end minute is discovered, not on the clock)."""
        start = self.clock.window_start(window)
        if self.clock.is_extra_time(window):
            end = self.feed.last_known_minute()
        else:
            end = self.clock.window_end(window)
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _on_lock(self, window: int, preds: list[Prediction], active_id: str,
                 use_power: bool) -> WindowReport:
        """Bridge from the screen: resolve `window` against the live feed, append any score
        events, and return the report the screen renders inline (no cinematic screen)."""
        actuals = self._window_actuals_for(window)
        # The live screen already reserved this player on the roster when the window locked,
        # so resolution must not spend it again (mark_used=False).
        res = self.session.resolve_window(window=window, predictions=preds,
                                          active_id=active_id, use_power=use_power,
                                          actuals=actuals, mark_used=False)
        for ev in res.score_events:
            self.score_codes.append(ev.to_code())
        return build_window_report(
            window=window, predictions=preds, actuals=actuals,
            stat_labels=_STAT_LABELS,
            success_value=self.session.success_meter.value,
            concede_value=self.session.concede_meter.value,
            success_threshold=_THRESH, concede_threshold=_THRESH_C,
            success_fired=res.success_fired, concede_fired=res.concede_fired,
            success_shot=res.success_shot, concede_shot=res.concede_shot)

    def _to_final(self) -> None:
        team, opp = aggregate(self.score_codes)
        title = _FULLTIME_LABEL if self.half == 2 else _HALFTIME_LABEL
        self._submit_highscore(team, opp)
        self._clear_resume()   # half finished -> never resume into a completed half
        self.app.set_screen(FinalScreen(self.app, team, opp, None,
                                        on_continue=self.to_picker, title=title))

    def _clear_resume(self) -> None:
        if self.on_resume_clear is not None:
            try:
                self.on_resume_clear()
            except Exception:
                pass

    def _submit_highscore(self, goals_for: int, goals_against: int) -> None:
        """Fire-and-forget the player's final scoreline to the public board as the half ends.
        Fully guarded: a relay/network/event-loop failure here must NEVER block the transition
        to the FinalScreen, so every failure mode is swallowed."""
        if self.highscore_client is None or not self.username or not self.game_label:
            return
        try:
            asyncio.ensure_future(self.highscore_client.submit(
                self.game_label, self.username, goals_for, goals_against))
        except Exception:
            pass


class DungeonSimFlow:
    """Single-device cooperative dungeon crawl over a recorded match.

    Splash -> Pre-game -> Shop(H1) -> 3 windows -> Shop(H2) -> 3 windows -> Final(% done).
    Deterministic: one fixed RNG seed, no relay, no API. The pure CrawlSession owns all
    economy / loadout / resolution; this flow only sequences screens and extracts the
    per-window actuals from the feed."""

    def __init__(self, app: "App", feed: ReplayFeed, pool: list[DraftedAthlete],
                 sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.sim = sim
        self.app.global_handler = sim.handle_global
        self.app.overlay = sim.draw_overlay
        self.session = CrawlSession(party_size=_DUNGEON_PARTY_SIZE, pool=pool,
                                    rng=random.Random(_RNG_SEED))
        self.window = 1

    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._after_splash, self.sim))

    def _after_splash(self) -> None:
        self.app.set_screen(PregameScreen(self.app, self._fixture(), self._to_shop, self.sim))

    def _fixture(self) -> dict:
        meta = getattr(self.feed, "meta", {})
        label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        return {
            "home": meta.get("home_team", _PREGAME["default_home_team"]),
            "away": meta.get("away_team", _PREGAME["default_away_team"]),
            "competition": meta.get("title", _PREGAME["default_competition"]),
            "label": label,
        }

    def _to_shop(self) -> None:
        self.app.set_screen(ShopScreen(self.app, self.session, self._after_shop, self.sim))

    def _after_shop(self) -> None:
        self.window = 1
        self._play_window()

    def _label(self) -> str:
        half_label = _HALF_LABEL if self.session.half == 1 else _SECOND_HALF_LABEL
        return f"{half_label} -- Window {self.window}/{_WINDOWS_PER_HALF}"

    def _play_window(self) -> None:
        self.app.set_screen(DungeonPlayScreen(
            self.app, self.session, self.feed, self.window, self._label(),
            self._on_descend, self._on_continue, self.sim))

    def _window_actuals(self) -> dict:
        start = (self.session.half - 1) * _HALF_MIN + (self.window - 1) * _WINDOW_MIN
        end = start + _WINDOW_MIN
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _on_descend(self, lines: dict) -> WindowResult:
        return self.session.resolve_window([lines], self._window_actuals(), self._label())

    def _on_continue(self) -> None:
        if not self.session.half_over():
            self.window += 1
            self._play_window()
        elif self.session.half == 1:
            self._to_half_recap()
        else:
            self._to_final()

    def _to_half_recap(self) -> None:
        """End-of-H1 recap, then Continue begins the second half and re-enters the shop."""
        def go() -> None:
            self.session.begin_second_half()
            self._to_shop()
        total = total_tiles_game(self.session.party_size)
        self.app.set_screen(DungeonHalfScreen(
            self.app, self.session.percent(), self.session.cleared_total(), total,
            [("You", self.session.treasury)], self.session.log[-_RECAP_LOG_LINES:],
            on_continue=go, title=_HALFTIME_LABEL, sim=self.sim))

    def _to_final(self) -> None:
        self.app.set_screen(DungeonFinalScreen(
            self.app, self.session.percent(), self.session.cleared_total(),
            total_tiles_game(self.session.party_size),
            on_continue=None, title=_FULLTIME_LABEL))


class DungeonPartyFlow:
    """Online cooperative crawl. The leader holds the authoritative CrawlSession inside the
    PartyCoordinator; followers poll and render. SIM mode runs over a recorded feed with manual
    window advance (deterministic, testable). LIVE mode (attach_live + start_dungeon_party_live)
    runs over the real feed on the match clock; that wiring reuses this flow's steps."""

    def __init__(self, app: "App", feed: ReplayFeed, pool: list[DraftedAthlete],
                 coord: PartyCoordinator, sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.coord = coord
        self.sim = sim
        self.app.global_handler = sim.handle_global
        self.app.overlay = sim.draw_overlay
        self.window = 1
        self._local_shop = None
        self.live = False
        # is_follower_live: a LIVE follower that must build its machinery from the shared blob
        # (set by start_dungeon_party_live for non-lead clients). Distinct from self.live, which
        # only flips True once attach_live / attach_live_from_blob has run.
        self.is_follower_live = False
        # LIVE wiring (set by attach_live / attach_live_from_blob); None/False in SIM mode.
        self.feed_client: Optional[FeedClient] = None
        self.live_feed: Optional[LiveFeed] = None
        self.fixture_id: int = 0
        self.clock: Optional[HalfClock] = None
        self.kickoff_epoch: float = 0.0   # set by start_dungeon_party_live before play
        self._play_screen: Optional[PartyPlayScreen] = None

    # -- LIVE mode wiring (Task 14) -----------------------------------------

    def _match_summary(self) -> dict:
        """Build the match-summary dict shared into the party blob from the live feed."""
        return {"home": self.live_feed.home_team(), "away": self.live_feed.away_team(),
                "home_goals": self.live_feed.home_goals(),
                "away_goals": self.live_feed.away_goals(),
                "minute": self.live_feed.current_minute(),
                "status": self.live_feed.status_short()}

    def attach_live(self, feed_client: FeedClient, live_feed: LiveFeed,
                    fixture_id: int, clock: HalfClock) -> None:
        """LIVE mode: the leader fetches the feed and shares match/pool; the match clock
        drives window boundaries. clock is a HalfClock (half-aware start_minute)."""
        self.feed_client = feed_client
        self.live_feed = live_feed
        self.fixture_id = int(fixture_id)
        self.clock = clock
        self.feed = live_feed
        self.live = True

    def attach_live_from_blob(self) -> bool:
        """Follower LIVE wiring: build this client's live machinery from the leader's shared
        party blob instead of resolving the fixture or polling the sports API. The leader has
        already pushed fixture_id + kickoff_iso (and the lineup pool) into the blob; the
        follower seeds a LiveFeed kickoff from kickoff_iso, attaches it with a fresh half-1
        clock, and estimates kickoff_epoch from kickoff_iso. Returns True once attached.

        Followers still hold a FeedClient(is_lead=False) but never call get_feed /
        get_live_fixtures: leader_poll_feed early-returns for non-leaders, so the follower's
        live feed stays empty and all display comes from the blob (coord.view()['match'])."""
        if self.live:
            return True
        p = self.coord.party
        if p is None or not p.fixture_id:
            return False
        feed = LiveFeed()
        feed.seed_kickoff(p.kickoff_iso or "")
        now_now = time.time()
        secs = seconds_to_kickoff(feed.kickoff_iso(), now_now)
        self.kickoff_epoch = now_now + secs if secs is not None else now_now
        # feed_client is supplied by the caller (FeedClient is_lead=False); reuse it so the
        # follower never constructs a lead feed client.
        self.attach_live(self.feed_client, feed, int(p.fixture_id),
                         HalfClock(_HALF_MIN, _WINDOW_MIN))
        return True

    async def leader_poll_feed(self) -> None:
        """Leader only: fetch one relay snapshot, record it, and share the match summary
        (+ the lineup pool once it arrives) into the blob. Fully guarded -- a network
        failure here must never crash play; followers render from the blob and never poll
        the sports API."""
        if not self.live or not self.coord.is_leader:
            return
        try:
            snap = await self.feed_client.get_feed(self.fixture_id)
            self.live_feed.record(snap)
            match = self._match_summary()
            pool_rows = None
            if not self.coord.party.pool and self.live_feed.has_lineups():
                pool_rows = self.live_feed.lineups()
            await self.coord.leader_share_match(match, pool_rows=pool_rows,
                                                fixture_id=self.fixture_id,
                                                kickoff_iso=self.live_feed.kickoff_iso() or "")
        except Exception:
            return

    def live_actuals_for(self, window: int) -> dict:
        """Actuals (per-stat deltas) from the live feed for one window. A live Extra-Time
        window resolves over everything polled so far (its end minute is discovered via
        last_known_minute, not on the clock) -- mirrors LiveFlow._window_actuals_for."""
        start = self.clock.window_start(window)
        if self.clock.is_extra_time(window):
            end = self.live_feed.last_known_minute()
        else:
            end = self.clock.window_end(window)
        a = self.live_feed.snapshot_at(start)
        b = self.live_feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._to_lobby, self.sim))

    def _to_lobby(self) -> None:
        # The leader picks the match BEFORE the lobby (FixtureSelectScreen runs first in the
        # leader path), so the lobby button always STARTS the crawl -- it never picks. Labelling
        # it "Pick match" would be misleading; keep "Start crawl" for both SIM and LIVE.
        label = "Start crawl"
        self.app.set_screen(PartyLobbyScreen(
            self.app, self.coord, on_start=self._leader_start, on_advance=self._to_shop,
            start_label=label, sim=self.sim))

    def _leader_start(self) -> None:
        asyncio.ensure_future(self._leader_share_then_start())

    async def _leader_share_then_start(self) -> None:
        """LIVE leader: publish the fixture + lineup pool into the blob BEFORE flipping the
        lobby to shop, so a follower (who never resolves the fixture or polls the sports API)
        can build its draft pool and shop catalog from the shared rows. SIM has no feed to
        share and goes straight to leader_start."""
        if self.live and self.live_feed is not None and self.live_feed.has_lineups():
            match = self._match_summary()
            await self.coord.leader_share_match(
                match, pool_rows=self.live_feed.lineups(), fixture_id=self.fixture_id,
                kickoff_iso=self.live_feed.kickoff_iso() or "")
        await self.coord.leader_start()

    def _sync_pool_from_blob(self) -> None:
        """Follower path: the leader shared the lineup pool into the party blob; build (or
        rebuild) the local draft/shop pool from those rows. The leader already holds a pool
        from the feed, so only an empty local pool is replaced. Idempotent and guarded -- a
        malformed row must never crash the shop."""
        if self.pool:
            return
        rows = self.coord.party.pool if self.coord.party else []
        if not rows:
            return
        try:
            self.pool = _pool_from_rows(rows)
        except (KeyError, TypeError, ValueError):
            self.pool = []

    def _to_shop(self) -> None:
        # Follower LIVE: attach this client's live machinery from the leader's shared blob
        # (fixture + kickoff) before the first shop, so the play phase runs the live path with
        # a correct clock. No-ops for the leader (already live) and for SIM.
        if self.is_follower_live:
            self.attach_live_from_blob()
        self._sync_pool_from_blob()
        budget = max(1, self.coord.shop_budget())
        local = CrawlSession(party_size=1, pool=self.pool, rng=random.Random(_RNG_SEED),
                             half=self.coord.half(), treasury=budget)
        self._local_shop = local
        self.app.set_screen(ShopScreen(self.app, local, self._after_shop, self.sim))

    def _after_shop(self) -> None:
        item_ids = [it.item_id for it in self._local_shop.loadouts[0].items]
        asyncio.ensure_future(self._submit_loadout_then_wait(item_ids,
                                                             self._local_shop.treasury))

    async def _submit_loadout_then_wait(self, item_ids: list, treasury: int) -> None:
        await self.coord.submit_loadout(item_ids, treasury)
        await self.coord.refresh()
        if self.coord.is_leader:
            await self.coord.leader_try_reconcile_shop()
        self.window = 1
        self._play_window()

    def _label(self) -> str:
        half_label = _HALF_LABEL if self.coord.half() == 1 else _SECOND_HALF_LABEL
        return f"{half_label} -- Window {self.window}/{_WINDOWS_PER_HALF}"

    def _play_window(self) -> None:
        if self.live:
            self._play_window_live()
            return
        self.app.set_screen(PartyPlayScreen(self.app, self.coord, self.window, self._label(),
                                            self._on_continue, require_all=True, sim=self.sim))

    def _play_window_live(self) -> None:
        """LIVE window: the leader's poll fetches+shares the feed (on_poll) and the match
        clock drives the boundary. The player edits one window ahead; when the playing clock
        crosses into this window (editing_window advances past it), force_resolve auto-submits
        and the leader resolves with require_all=False. Mirrors LiveFlow's poll-driven,
        clock-advanced window loop."""
        screen = PartyPlayScreen(self.app, self.coord, self.window, self._label(),
                                 self._on_continue, require_all=False,
                                 on_poll=self._live_poll,
                                 can_resolve=self._live_data_ready, sim=self.sim)
        self._play_screen = screen
        self.app.set_screen(screen)

    def _live_data_ready(self, window: int) -> bool:
        """LIVE resolution gate: True once the live feed actually covers this window's data,
        so leader_try_resolve grades against real per-window deltas (not stale zeros). The
        clock boundary locks the picks (force_resolve); THIS defers the scoring until the
        query has the data -- the 'queries happen in the window' behaviour. Mirrors the
        single-player live path's windows_ready() gate."""
        if self.clock is None or self.live_feed is None:
            return True
        match_over = self.live_feed.match_status() in (_HALFTIME_STATUS, _FINISHED_STATUS)
        return window_data_ready(self.live_feed.last_known_minute(), window,
                                 self.clock, match_over)

    async def _live_poll(self) -> None:
        """Per-poll LIVE hook (leader fetch+share, then clock-boundary check). Runs inside
        PartyPlayScreen's poll loop. Guarded so a network/clock failure never crashes play."""
        # leader_poll_feed self-guards its full network path (fetch/record/share); the guard
        # here protects the clock-boundary arithmetic, the one path not already covered.
        await self.leader_poll_feed()
        try:
            # Clock-driven boundary: once the match clock has advanced its editing window past
            # the window we are filling, that window's play time is over -> lock + resolve it.
            if self.clock is None or self._play_screen is None:
                return
            match_clock = MatchClock(self.kickoff_epoch, self.clock)
            if match_clock.editing_window(time.time()) > self.window:
                self._play_screen.force_resolve()
        except Exception:
            pass

    def actuals_for(self, window: int) -> dict:
        start = (self.coord.half() - 1) * _HALF_MIN + (window - 1) * _WINDOW_MIN
        end = start + _WINDOW_MIN
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _on_continue(self) -> None:
        if self.window < _WINDOWS_PER_HALF:
            self.window += 1
            self._play_window()
        elif self.coord.half() == 1:
            asyncio.ensure_future(self._advance_then_shop())
        else:
            asyncio.ensure_future(self._advance_then_finish())

    async def _advance_then_shop(self) -> None:
        if self.coord.is_leader:
            await self.coord.leader_advance_half()
        else:
            await self.coord.refresh()
        self._reanchor_half_two()
        self._to_half_recap()

    def _to_half_recap(self) -> None:
        """End-of-H1 party recap (leader and follower both see it). Continue enters the H2 shop.
        State was already advanced by the leader in _advance_then_shop; this only sequences UI."""
        v = self.coord.view()
        self.app.set_screen(DungeonHalfScreen(
            self.app, v["percent"], v["depth"], v["total"], v["members"],
            v["log"][-_RECAP_LOG_LINES:], on_continue=self._to_shop,
            title=_HALFTIME_LABEL, sim=self.sim))

    def _reanchor_half_two(self) -> None:
        """LIVE half 2: re-anchor the clock to absolute minutes 45-90 and re-estimate the
        kickoff epoch, exactly as LiveFlow's launch_half(2) does (flow.py launch_half). Without
        this the clock keeps start_minute=0, so live_actuals_for reads first-half minutes 0-45
        in the second half and the editing-window boundary check runs off a first-half anchor.
        The per-poll MatchClock self-corrects the estimate against the API minute."""
        if not self.live or self.clock is None:
            return
        self.clock = HalfClock(_HALF_MIN, _WINDOW_MIN, start_minute=_HALF_MIN)
        # Leader reads the live feed; a follower's feed is never polled, so it falls back to the
        # match minute the leader shared into the blob.
        minute = self.live_feed.current_minute() if (
            self.live_feed and self.live_feed.current_minute()) else int(
            self.coord.view().get("match", {}).get("minute", 0))
        in_half = max(0, minute - _HALF_MIN)
        self.kickoff_epoch = time.time() - in_half * 60

    async def _advance_then_finish(self) -> None:
        if self.coord.is_leader:
            await self.coord.leader_advance_half()
        else:
            await self.coord.refresh()
        v = self.coord.view()
        self.app.set_screen(DungeonFinalScreen(self.app, v["percent"], v["depth"], v["total"],
                                               on_continue=None, title=_FULLTIME_LABEL))


def start_dungeon_party(app: "App", username: str, sim_rel_path: str,
                        sim_mode: bool = True) -> None:
    """SIM cooperative party: a recorded match drives deterministic per-window actuals on
    every client; windows advance manually. The username (from UsernameScreen) is the party
    credential. LIVE entry is start_dungeon_party_live (Task 14)."""
    feed = ReplayFeed.from_file(sim_rel_path)
    pool = _pool_from_feed(feed)
    sim = SimMode(sim_mode)
    relay = RelayClient(CONFIG["relay"]["base_url"], api_path=CONFIG["relay"]["api_path"])

    def picked(party_number: int) -> None:
        coord = PartyCoordinator(relay=relay, party_id=party_number, username=username,
                                 pool=pool, actuals_fn=lambda w: flow.actuals_for(w))
        flow = DungeonPartyFlow(app, feed, pool, coord, sim)

        async def go() -> None:
            await coord.join()
            flow.start()
        asyncio.ensure_future(go())

    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    app.set_screen(PartyScreen(app, username, picked, sim))


def start_dungeon_party_live(app: "App", username: str, is_lead: bool = False,
                             sim_mode: bool = False) -> None:
    """LIVE cooperative party: the leader fetches the real match feed THROUGH the PHP relay
    (FeedClient is_lead) and shares the match summary + lineup pool into the party blob; the
    match clock drives the window boundaries. Followers NEVER call the sports API -- they read
    the relay cache for the pre-game wait and render the crawl from the leader's shared blob.

    Reuses the full live pre-game stack from start_live: party number (PartyScreen) ->
    fixture picker (FixtureSelectScreen) -> real-id resolution (LiveResolveScreen) -> lineup
    wait (LiveWaitScreen). Once lineups arrive the lineup pool is built from the feed, a
    PartyCoordinator + DungeonPartyFlow are constructed, the live feed/clock are attached, and
    the flow runs (lobby -> shop -> 3 clock-driven windows per half)."""
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    relay = RelayClient(CONFIG["relay"]["base_url"], api_path=CONFIG["relay"]["api_path"])
    feed_client = FeedClient(CONFIG["relay"]["base_url"],
                             feed_path=CONFIG["relay"]["feed_path"], is_lead=is_lead,
                             live_fixtures_path=CONFIG["relay"]["live_fixtures_path"])

    # FOLLOWER PATH (Spec Step 3): a non-lead client must NOT run the fixture picker / resolve /
    # lineup wait, and must NEVER resolve the fixture itself (two followers could otherwise pick
    # different matches). Instead it joins the party with an EMPTY pool, sits in the lobby polling
    # the relay, and once the leader's blob carries fixture_id + lineup pool it builds its live
    # machinery FROM THE BLOB (see DungeonPartyFlow.attach_live_from_blob + _sync_pool_from_blob,
    # invoked at _to_shop). The lobby auto-advances to shop when the leader flips the phase.
    if not is_lead:
        def picked_follower(party_number: int) -> None:
            coord = PartyCoordinator(
                relay=relay, party_id=party_number, username=username,
                pool=[], actuals_fn=lambda w: flow.live_actuals_for(w))
            flow = DungeonPartyFlow(app, LiveFeed(), [], coord, sim)
            flow.feed_client = feed_client   # is_lead=False; never calls get_feed
            flow.is_follower_live = True

            async def go() -> None:
                await coord.join()
                flow.start()
            asyncio.ensure_future(go())

        app.set_screen(PartyScreen(app, username, picked_follower, sim))
        return

    sched_cfg = _LIVE["schedule"]
    try:
        raw = load_data(f'{CONFIG["assets"]["data_dir"]}/{sched_cfg["file"]}')
    except (OSError, ValueError):
        raw = {"games": []}
    games = load_schedule(raw)
    # Party windows are the dungeon's 15-minute windows (windows_per_half = 3), NOT the
    # live half's 5-minute windows: the CrawlSession economy is built around 3 per half.
    party_clock = HalfClock(_HALF_MIN, _WINDOW_MIN)

    def picker() -> None:
        app.set_screen(FixtureSelectScreen(app, games, on_resolve, sched_cfg, sim))

    def on_resolve(fixture_id: int) -> None:
        game = next((g for g in games if g.id == fixture_id), None)
        feed = LiveFeed()
        feed.seed_kickoff(game.kickoff_utc if game else "")
        home = game.home if game else ""
        away = game.away if game else ""

        def run_with(real_id: int) -> None:
            def after_lineups() -> None:
                pool = _pool_from_feed(feed)
                now_now = time.time()
                secs = seconds_to_kickoff(feed.kickoff_iso(), now_now)
                kickoff_epoch = now_now + secs if secs is not None else now_now

                def picked(party_number: int) -> None:
                    coord = PartyCoordinator(
                        relay=relay, party_id=party_number, username=username,
                        pool=pool, actuals_fn=lambda w: flow.live_actuals_for(w))
                    flow = DungeonPartyFlow(app, feed, pool, coord, sim)
                    flow.kickoff_epoch = kickoff_epoch
                    flow.attach_live(feed_client, feed, real_id, party_clock)

                    async def go() -> None:
                        await coord.join()
                        flow.start()
                    asyncio.ensure_future(go())

                app.set_screen(PartyScreen(app, username, picked, sim))

            app.set_screen(LiveWaitScreen(
                app, feed, feed_client, real_id, target_minute=None,
                on_ready=after_lineups, poll_seconds=_POLL_SECONDS, sim=sim,
                wait_for_lineups=True, on_back=picker))

        if home and away:
            app.set_screen(LiveResolveScreen(
                app, feed_client, home, away,
                kickoff_iso=(feed.kickoff_iso() or ""),
                on_resolved=run_with, poll_seconds=_RESOLVE_POLL_SECONDS,
                fallback_id=fixture_id, sim=sim, on_back=picker))
        else:
            run_with(fixture_id)

    picker()


def start_live(app: "App", fixture_id: int, sim_mode: bool = False,
               is_lead: bool = False, username: str = "", kickoff_utc: str = "",
               home: str = "", away: str = "") -> None:
    """Live single-player half. Park on a waiting screen until the API publishes the
    starting XI, then size the half from the live match clock and run the draft + windows.
    Only the lead client (is_lead) spends API-Football quota; followers read the cache.

    Live id resolution: when home/away are given (the picker path), the schedule's synthetic
    id is NOT a real API-Football id. A LiveResolveScreen first matches the picked teams to
    whatever World Cup match is in play now (live_fixtures.php) to learn the real id, then the
    rest of the flow runs against that real id. The --live single-fixture path passes a real
    id directly with no home/away and skips resolution.

    Warm cache: on entry the last saved relay snapshot for this user+fixture is replayed
    into the feed so lineups/score/clock show instantly (no API call); each successful live
    poll persists the fresh snapshot back so the next session is warm too.

    kickoff_utc (from the picked schedule game) seeds the pre-game countdown for any game,
    not just those listed in live.fixtures; a real poll's fixture.date still overrides it."""
    feed = LiveFeed()
    for fx in (_LIVE.get("fixtures") or []):
        if fx.get("id") == fixture_id and fx.get("kickoff"):
            feed.seed_kickoff(fx["kickoff"])
            break
    feed.seed_kickoff(kickoff_utc)   # picked-game kickoff wins (seed_kickoff no-ops if "")

    feed_client = FeedClient(CONFIG["relay"]["base_url"],
                             feed_path=CONFIG["relay"]["feed_path"], is_lead=is_lead,
                             live_fixtures_path=CONFIG["relay"]["live_fixtures_path"])
    highscore_client = HighscoreClient(CONFIG["relay"]["base_url"],
                                       path=CONFIG["relay"]["highscore_path"])
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay

    def to_picker() -> None:
        start_live_select(app, sim_mode=sim_mode, is_lead=is_lead, username=username)

    def no_half_left() -> None:
        app.set_screen(RevealScreen(
            app, ["This match has no half left to play.", "Pick another match."],
            on_continue=to_picker))

    def run_with(real_id: int) -> None:
        """Everything downstream of id resolution: warm the cache for the REAL id, then run
        the lineups wait -> draft -> live windows against it."""
        store = LocalStore()
        key = cachep.cache_key(username, real_id)
        blob = cachep.deserialize(store.get(key))
        if blob and isinstance(blob.get("snapshot"), dict):
            feed.record(blob["snapshot"])   # warm display instantly, no API call

        def persist(snap: dict) -> None:
            store.set(key, cachep.serialize(cachep.make_blob(snap, time.time())))

        def launch_half(half: int) -> None:
            start_minute = 0 if half == 1 else _HALF_MIN
            clock = HalfClock(_HALF_MIN, _WINDOW_MIN, start_minute=start_minute)
            now_now = time.time()
            if half == 1:
                secs = seconds_to_kickoff(feed.kickoff_iso(), now_now)
                kickoff_epoch = now_now + secs if secs is not None else now_now
            else:
                in_half = max(0, feed.current_minute() - _HALF_MIN)
                kickoff_epoch = now_now - in_half * 60          # estimate; screen re-aligns
            elapsed_in_half = max(0, feed.current_minute() - start_minute)
            plan = live_plan(elapsed_in_half, feed.match_status(), clock)
            if not plan.scored_windows:
                no_half_left()
                return
            pool = _pool_from_feed(feed)
            game_label = f"{feed.home_team() or home} v {feed.away_team() or away}".strip()

            # Resume: load any saved point for this user+fixture+half; save on every change and
            # clear it when the half ends. Keyed per half so the two halves never clobber.
            rkey = live_resume.resume_key(username, real_id, half)
            resume_blob = live_resume.parse(store.get(rkey))

            def save_resume(blob_json: str) -> None:
                store.set(rkey, blob_json)

            def clear_resume() -> None:
                store.set(rkey, "")

            LiveFlow(app, feed, feed_client, real_id, pool, half, clock,
                     kickoff_epoch, sim, to_picker, on_snapshot=persist,
                     username=username, game_label=game_label,
                     highscore_client=highscore_client,
                     resume_blob=resume_blob, on_resume_save=save_resume,
                     on_resume_clear=clear_resume).start()

        def begin() -> None:
            choice = pick_half(feed.status_short(), feed.current_minute(),
                               _HALF_MIN, _JOIN_CUTOFF)
            if choice.half is None:
                no_half_left()
            elif choice.needs_wait:
                app.set_screen(LiveWaitScreen(
                    app, feed, feed_client, real_id, target_minute=None,
                    on_ready=lambda: launch_half(2), poll_seconds=_POLL_SECONDS,
                    sim=sim, wait_for_second_half=True))
            else:
                launch_half(choice.half)

        app.set_screen(LiveWaitScreen(app, feed, feed_client, real_id,
                                      target_minute=None, on_ready=begin,
                                      poll_seconds=_POLL_SECONDS, sim=sim,
                                      wait_for_lineups=True, on_back=to_picker))

    if home and away:
        app.set_screen(LiveResolveScreen(
            app, feed_client, home, away,
            kickoff_iso=(feed.kickoff_iso() or kickoff_utc),
            on_resolved=run_with, poll_seconds=_RESOLVE_POLL_SECONDS,
            fallback_id=fixture_id, sim=sim, on_back=to_picker))
    else:
        run_with(fixture_id)


def start_live_select(app: "App", sim_mode: bool = False,
                      is_lead: bool = False, username: str = "") -> None:
    """Show the dynamic live-match picker, then play the chosen game live. Reads the
    curated schedule (assets/data/schedule.json via live.schedule); the rolling-window
    viewer orders games soonest-first and lets the player tap any not-yet-finished game.
    Web/no-argument entry point for match day."""
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    sched_cfg = _LIVE["schedule"]
    try:
        raw = load_data(f'{CONFIG["assets"]["data_dir"]}/{sched_cfg["file"]}')
    except (OSError, ValueError):
        raw = {"games": []}                      # empty-state screen, never a crash
    games = load_schedule(raw)

    def picked(fixture_id: int) -> None:
        game = next((g for g in games if g.id == fixture_id), None)
        start_live(app, fixture_id, sim_mode=sim_mode, is_lead=is_lead,
                   username=username, kickoff_utc=(game.kickoff_utc if game else ""),
                   home=(game.home if game else ""), away=(game.away if game else ""))

    app.set_screen(FixtureSelectScreen(app, games, picked, sched_cfg, sim))


def start_app(app: "App", sim_mode: bool = False) -> None:
    """Top web entry: ask for a username, then show the mode menu. A username matching
    config.client.lead_username (case-insensitive) becomes the lead client that polls
    the live scores; everyone else free-rides on the website cache."""
    def submitted(username: str) -> None:
        is_lead = username.strip().lower() == _LEAD_NAME.lower()
        start_launcher(app, sim_mode=sim_mode, is_lead=is_lead, username=username)

    app.set_screen(UsernameScreen(app, submitted))


def start_launcher(app: "App", sim_mode: bool = False, is_lead: bool = False,
                   username: str = "") -> None:
    """Web entry: choose 'Live match' (real fixtures + relay) or 'Test game' (an offline
    recorded match, no API/no waiting) so the full flow can be tried without a live game."""
    # The simulated party crawl plays its recorded match deterministically (downstream
    # sim_mode=True), but the PICKER inherits the launcher's sim_mode so a real web user
    # (sim_mode=False) taps a game rather than having the first one auto-picked.
    def go_party() -> None:
        start_sim_select(app, lambda path: start_dungeon_party(app, username, path,
                                                               sim_mode=sim_mode),
                         sim_mode=sim_mode)

    def go_party_live() -> None:
        start_dungeon_party_live(app, username, is_lead=is_lead, sim_mode=sim_mode)

    # Two modes only: the live dungeon crawl and its simulated (recorded-match) twin.
    options = [
        (_LAUNCHER["party_live_label"], go_party_live),
        (_LAUNCHER["party_label"], go_party),
    ]
    app.set_screen(LauncherScreen(app, options))


def start_sim_select(app: "App", on_pick: Callable[[str], None],
                     sim_mode: bool = True) -> None:
    """Show the recorded-simulation picker, then run on_pick(rel_path) for the chosen game.
    Every offline mode (test game, dungeon crawl, dungeon party) begins here so all modes
    start with a game list. SIM auto-picks the first game so headless/demo paths keep moving.
    A missing/empty simulations dir yields an empty-state screen, never a crash."""
    sim = SimMode(sim_mode)
    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    games = list_simulations(ROOT, _SIMS_DIR)
    app.set_screen(SimGameSelectScreen(app, games, on_pick, sim))


def start_simulation(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    Flow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()


def start_dungeon_sim(app: "App", sim_rel_path: str, sim_mode: bool = True) -> None:
    feed = ReplayFeed.from_file(sim_rel_path)
    DungeonSimFlow(app, feed, _pool_from_feed(feed), SimMode(sim_mode)).start()


def start(app: "App", sim_mode: bool = False) -> None:
    Flow(app, MockFeed(_demo_script()), _demo_pool(), SimMode(sim_mode)).start()
