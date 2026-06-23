# src/game/window_resolver.py
"""Leader-authoritative resolution of one 15-minute window: grade every fighter's predictions
into bands -> tile advance, accrue Power from goal predictions, walk the party along the tile
track resolving any monster gate crossed, and award gold. Pure: rng is injected."""
import random
from dataclasses import dataclass, field

from src.game.bands import Band, grade_progress, window_color
from src.game.dungeon import (DungeonState, gate_step, monster_count, monster_name,
                              resolve_gate)
from src.game.power import power_gain
from src.game.treasury import gate_loot_gold, tile_gold
from src.utils.constants import CONFIG, load_data

_PROGRESS = ["shot", "corner", "card", "foul"]
_MAX_WOUNDS = int(CONFIG["dungeon"]["max_wounds"])

# Canonical stat order + labels (goal first, then the four progress stats). Pure data,
# no pygame -- used to build the per-prediction outcomes the UI underlines/colors.
_STATS_MENU = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
STAT_CODES: list[str] = [s["code"] for s in _STATS_MENU]
_STAT_LABELS: dict[str, str] = {s["code"]: s["label"] for s in _STATS_MENU}


def _color_key(band: Band) -> str:
    """Map an accuracy band to the three feedback colors used in the play screens."""
    if band.key in ("exact", "close"):
        return "green"
    if band.is_big_miss:
        return "red"
    return "orange"


@dataclass(frozen=True)
class StatResult:
    """One prediction's outcome for the underline/color strip + the mixed log."""
    code: str
    label: str
    predicted: int
    actual: int
    band_label: str
    color_key: str


def build_stat_results(lines: dict, actuals: dict) -> list[StatResult]:
    """Grade one fighter's predicted `lines` against `actuals` into per-stat outcomes, in the
    canonical stat order. Pure -- shared by the resolver and the play screens (which grade the
    local player's own picks against the pushed actuals)."""
    results: list[StatResult] = []
    for code in STAT_CODES:
        predicted = int(lines.get(code, 0))
        actual = int(actuals.get(code, 0))
        band = grade_progress(predicted, actual)
        results.append(StatResult(code=code, label=_STAT_LABELS[code],
                                   predicted=predicted, actual=actual,
                                   band_label=band.label, color_key=_color_key(band)))
    return results


@dataclass
class PartyGear:
    """Party-wide combat aids for this window (best weapon/armor across fighters, one queued
    consumable value, reroll availability). Filled by the caller from the fighters' loadouts."""
    weapon_bonus: int = 0
    armor_soak: int = 0
    has_reroll: bool = False
    consumable_value: int = 0


@dataclass(frozen=True)
class WindowResult:
    tiles_advanced: int
    power_gained: int
    color: str
    gold: int
    gates: list = field(default_factory=list)
    log: list = field(default_factory=list)
    finished: bool = False
    stat_results: list = field(default_factory=list)
    actuals: dict = field(default_factory=dict)


def resolve_window(rng: random.Random, state: DungeonState, gear: PartyGear, fighter_lines: list,
                   actuals: dict, window_label: str) -> WindowResult:
    log: list = []
    tiles = 0
    has_big_miss = False
    power_gained = 0

    # The horde engaged this window is fixed by the threat the party walked in with (scaled to
    # actual party size); graded tiles below slay monsters, leftovers carry forward.
    engaged = monster_count(state.half, state.party_size, state.threat)

    for lines in fighter_lines:
        for stat in _PROGRESS:
            band = grade_progress(int(lines.get(stat, 0)), int(actuals.get(stat, 0)))
            tiles += band.step
            if band.is_big_miss:
                has_big_miss = True
        power_gained += power_gain(int(lines.get("goal", 0)), int(actuals.get("goal", 0)))

    state.power += power_gained
    if has_big_miss:
        state.threat += 1
    color = window_color(tiles, has_big_miss)

    # Per-prediction outcomes for the FIRST fighter's lines, in canonical stat order.
    # Goal is graded for display only (its tile/power effect is unchanged above).
    first_lines = fighter_lines[0] if fighter_lines else {}
    used_actuals = {code: int(actuals.get(code, 0)) for code in STAT_CODES}
    stat_results = build_stat_results(first_lines, used_actuals)

    log.append(f"{window_label}  party advance +{tiles} ({color.upper()})")
    for sr in stat_results:
        log.append(f"  PRED   {sr.label} {sr.predicted} vs {sr.actual} -> "
                   f"{sr.band_label} ({sr.color_key.upper()})")
    if power_gained:
        log.append(f"  POWER  goal -> +{power_gained} Power (now {state.power})")

    gold = 0
    gates: list = []
    step = gate_step(state.half)

    if tiles <= 0:
        state.depth = max(0, state.depth + tiles)
    else:
        remaining = tiles
        while remaining > 0 and not state.finished:
            next_gate = ((state.depth // step) + 1) * step
            advance = min(remaining, next_gate - state.depth)
            for _ in range(advance):
                state.depth += 1
                gold += tile_gold(state.gates_passed, state.power)
                if state.depth >= state.total_tiles:
                    state.finished = True
                    break
            remaining -= advance
            if state.finished:
                break
            if state.depth == next_gate:
                outcome = resolve_gate(
                    rng, gear.weapon_bonus, gear.armor_soak, state.power,
                    state.half, state.party_size, state.threat,
                    consumable_value=gear.consumable_value, reroll=gear.has_reroll)
                gear.consumable_value = 0   # spent at this gate
                gates.append(outcome)
                if outcome.passed:
                    state.gates_passed += 1
                    loot = gate_loot_gold(state.power)
                    gold += loot
                    log.append(f"  GATE   diff {outcome.difficulty} roll {outcome.roll} -> PASS +{loot}g")
                else:
                    state.depth = max(0, state.depth - outcome.tiles_lost)
                    state.wounds += 1
                    log.append(
                        f"  GATE   diff {outcome.difficulty} roll {outcome.roll} -> FAIL "
                        f"(soak {outcome.soaked}, -{outcome.tiles_lost} tiles, wound {state.wounds})")
                    if state.wounds >= _MAX_WOUNDS:
                        state.finished = True
                        log.append("  CRAWL  party downed -- half ends")
                    # A failed gate halts the party: remaining tiles this window are forfeited.
                    break

    # Monsters slain = tiles advanced this window (capped at the engaged horde); any unslain
    # carry into threat so next window's horde + gate difficulty grow ("allocated the ones
    # left"). Stacks with the flat +1 a big miss already added above.
    kills = min(engaged, max(0, tiles))
    leftover = engaged - kills
    if leftover > 0:
        state.threat += leftover
        log.append(f"  HORDE  {leftover} {monster_name(state.half)} unslain "
                   f"-> threat {state.threat}")

    log.append(f"  DEPTH  {state.depth}/{state.total_tiles}")
    return WindowResult(tiles_advanced=tiles, power_gained=power_gained, color=color,
                        gold=gold, gates=gates, log=log, finished=state.finished,
                        stat_results=stat_results, actuals=used_actuals)
