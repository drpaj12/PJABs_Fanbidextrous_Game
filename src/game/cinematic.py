# src/game/cinematic.py
"""Pure (no pygame) builder: one window's resolution -> ordered animation beats.

The UI renders beats in order. For METER beats it animates the bar from the prior
displayed value to `value`. EXPLODE/GOAL/CONCEDE beats trigger flashes. The data here
is a dramatization of what resolve_window already computed -- it adds no game logic.
"""
from dataclasses import dataclass, field
from src.game.prediction import Prediction, grade
from src.game.scoring import ScoreEvent

TICK = "tick"          # a graded prediction is revealed
METER = "meter"        # a meter advances to `value`
EXPLODE = "explode"    # a meter reached threshold; flash + reset to 0
SHOT = "shot"          # a shot is taken
GOAL = "goal"          # shot scored for us
CONCEDE = "concede"    # shot scored against us
MISS = "miss"          # shot missed
SUMMARY = "summary"    # final tally


@dataclass
class Beat:
    kind: str
    meter: str = ""        # "success" | "concede" | ""
    value: int = 0         # meter display value AFTER this beat
    threshold: int = 0
    label: str = ""
    detail: str = ""


@dataclass
class CinematicScript:
    beats: list[Beat] = field(default_factory=list)
    team_delta: int = 0
    opp_delta: int = 0


def _outcome(g) -> str:
    if g.success_credit >= 2:
        return "hit"
    if g.success_credit == 1:
        return "near"
    return "miss"


def _meter_track(beats: list[Beat], meter: str, before: int, after: int,
                 fired: bool, threshold: int) -> None:
    """Append the meter's fill beats. If it fired, fill to threshold, EXPLODE, then
    resume from 0 to `after`."""
    if fired:
        beats.append(Beat(METER, meter=meter, value=threshold, threshold=threshold))
        beats.append(Beat(EXPLODE, meter=meter, value=0, threshold=threshold))
        if after > 0:
            beats.append(Beat(METER, meter=meter, value=after, threshold=threshold))
    elif after != before:
        beats.append(Beat(METER, meter=meter, value=after, threshold=threshold))


def build_cinematic_script(
    predictions: list[Prediction],
    actuals: dict[str, int],
    success_before: int, success_after: int, success_fired: bool,
    concede_before: int, concede_after: int, concede_fired: bool,
    threshold: int,
    score_events: list[ScoreEvent],
    stat_labels: dict[str, str],
) -> CinematicScript:
    beats: list[Beat] = []

    # 1) Reveal each prediction.
    for p in predictions:
        g = grade(p, actuals.get(p.stat_code, 0))
        beats.append(Beat(
            TICK, label=stat_labels.get(p.stat_code, p.stat_code),
            detail=_outcome(g)))

    # 2) Attack meter fills (+ explode if it fired).
    _meter_track(beats, "success", success_before, success_after,
                 success_fired, threshold)

    # 3) For-side shot resolution.
    team_delta = 0
    for ev in score_events:
        if ev.side != "for":
            continue
        beats.append(Beat(SHOT, meter="success"))
        if ev.scored:
            beats.append(Beat(GOAL, label="GOALLLLL!!!"))
            team_delta += 1
        else:
            beats.append(Beat(MISS, label="no goal"))

    # 4) Danger meter fills (+ explode if it fired).
    _meter_track(beats, "concede", concede_before, concede_after,
                 concede_fired, threshold)

    # 5) Against-side shot resolution.
    opp_delta = 0
    for ev in score_events:
        if ev.side != "against":
            continue
        beats.append(Beat(SHOT, meter="concede"))
        if ev.scored:
            beats.append(Beat(CONCEDE, label="CONCEDED"))
            opp_delta += 1
        else:
            beats.append(Beat(MISS, label="cleared"))

    beats.append(Beat(SUMMARY))
    return CinematicScript(beats=beats, team_delta=team_delta, opp_delta=opp_delta)
