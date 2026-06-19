# src/game/session.py
"""Per-player session state: resolves one window's predictions into meter/score changes."""
import random
from dataclasses import dataclass, field
from typing import Optional
from src.game.athlete import DraftedAthlete
from src.game.roster import Roster
from src.game.prediction import Prediction, grade
from src.game.meters import Meter
from src.game.powers import this_window_effect, next_window_effect, conversion_for
from src.game.shot import resolve_shot, pick_concede_attacker
from src.game.scoring import ScoreEvent
from src.utils.constants import CONFIG


@dataclass(frozen=True)
class ShotOutcome:
    """The single shot a meter earns when it fires: who took it and whether it scored.

    Local detail for the results panel only -- not transmitted (each client re-derives it).
    """
    shooter_name: str
    archetype: str
    conversion: float  # 0..1 chance the shot converted
    scored: bool


@dataclass
class WindowResolution:
    success_fired: bool
    concede_fired: bool
    score_events: list[ScoreEvent] = field(default_factory=list)
    success_shot: Optional[ShotOutcome] = None
    concede_shot: Optional[ShotOutcome] = None


class GameSession:
    def __init__(self, slot: int, roster: Roster, pool: list[DraftedAthlete],
                 rng: random.Random) -> None:
        self.slot = slot
        self.roster = roster
        self.pool = pool
        self.rng = rng
        self.success_meter = Meter(CONFIG["meter"]["success_threshold"])
        self.concede_meter = Meter(CONFIG["meter"]["concede_threshold"])
        self._owned_ids = {a.athlete_id for a in roster.all_athletes()}
        self._pending_next: dict = {"kind": "none", "value": 0.0}

    def _apply_credit_effects(self, effect: dict, success: int, concede: int) -> tuple[int, int]:
        kind, val = effect["kind"], effect["value"]
        if kind == "success_credit_add":
            success += round(val)
        elif kind == "success_credit_mult":
            success = round(success * val)
        elif kind == "concede_credit_add":
            concede += round(val)
        elif kind == "concede_credit_mult":
            concede = round(concede * val)
        return success, concede

    def resolve_window(self, window: int, predictions: list[Prediction],
                       active_id: str, use_power: bool, actuals: dict[str, int]) -> WindowResolution:
        active = self.roster.get(active_id)
        self.roster.use(active_id)

        success = concede = 0
        for p in predictions:
            g = grade(p, actuals.get(p.stat_code, 0))
            success += g.success_credit
            concede += g.concede_credit

        # Pending next-window effect from the previous window's power.
        success, concede = self._apply_credit_effects(self._pending_next, success, concede)
        self._pending_next = {"kind": "none", "value": 0.0}

        conversion_bonus = 0.0
        negate_concede = False
        if use_power:
            tw = this_window_effect(active)
            if tw["kind"] == "conversion_add":
                conversion_bonus = tw["value"]
            elif tw["kind"] == "negate_concede_shot":
                negate_concede = True
            else:
                success, concede = self._apply_credit_effects(tw, success, concede)
            self._pending_next = next_window_effect(active)

        success = max(0, success)
        concede = max(0, concede)

        events: list[ScoreEvent] = []
        success_shot: Optional[ShotOutcome] = None
        success_fired = self.success_meter.add(success)
        if success_fired:
            scored = resolve_shot(active, self.rng, bonus=conversion_bonus)
            events.append(ScoreEvent(self.slot, window, "for", scored))
            success_shot = ShotOutcome(active.name, active.archetype,
                                       conversion_for(active) + conversion_bonus, scored)

        concede_shot: Optional[ShotOutcome] = None
        concede_fired = self.concede_meter.add(concede)
        if concede_fired:
            if negate_concede:
                events.append(ScoreEvent(self.slot, window, "against", False))
                concede_shot = ShotOutcome("Opponent", "", 0.0, False)
            else:
                attacker = pick_concede_attacker(self.pool, self._owned_ids, self.rng)
                scored = resolve_shot(attacker, self.rng)
                events.append(ScoreEvent(self.slot, window, "against", scored))
                concede_shot = ShotOutcome(attacker.name, attacker.archetype,
                                           conversion_for(attacker), scored)

        return WindowResolution(success_fired, concede_fired, events,
                                success_shot, concede_shot)
