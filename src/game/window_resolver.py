# src/game/window_resolver.py
"""Leader-authoritative resolution of one 15-minute window: grade every fighter's predictions
into bands -> tile advance, accrue Power from goal predictions, walk the party along the tile
track resolving any monster gate crossed, and award gold. Pure: rng is injected."""
from dataclasses import dataclass, field

from src.game.bands import grade_progress, window_color
from src.game.dungeon import DungeonState, gate_step, resolve_gate
from src.game.power import power_gain
from src.game.treasury import gate_loot_gold, tile_gold
from src.utils.constants import CONFIG

_PROGRESS = ["shot", "corner", "card", "foul"]
_MAX_WOUNDS = int(CONFIG["dungeon"]["max_wounds"])


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


def resolve_window(rng, state: DungeonState, gear: PartyGear, fighter_lines: list,
                   actuals: dict, window_label: str) -> WindowResult:
    log: list = []
    tiles = 0
    has_big_miss = False
    power_gained = 0

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
    log.append(f"{window_label}  party advance +{tiles} ({color.upper()})")
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

    log.append(f"  DEPTH  {state.depth}/{state.total_tiles}")
    return WindowResult(tiles_advanced=tiles, power_gained=power_gained, color=color,
                        gold=gold, gates=gates, log=log, finished=state.finished)
