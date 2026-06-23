# src/game/crawl.py
"""Pure orchestration of one cooperative dungeon crawl across both halves: a shared party
treasury, one loadout per fighter, the live DungeonState, and the running crawl log. The UI
feeds in per-window actuals; this module owns all economy / loadout / resolution sequencing
so it stays fully testable. rng is injected (random.Random). Zero pygame, zero feed access."""
import random
from dataclasses import dataclass, field

from src.game.dungeon import DungeonState
from src.game.items import Item, build_catalog
from src.game.loadout import Loadout
from src.game.score import percent_complete, total_tiles_game
from src.game.treasury import base_treasury, second_half_multiplier
from src.game.window_resolver import PartyGear, WindowResult, resolve_window
from src.utils.constants import CONFIG

_WINDOWS_PER_HALF = int(CONFIG["game"]["windows_per_half"])


@dataclass
class CrawlSession:
    party_size: int
    pool: list                       # list[DraftedAthlete] from the match lineup
    rng: random.Random
    half: int = 1
    treasury: int = 0
    window_index: int = 0            # windows resolved in the current half
    cleared_prev_halves: int = 0     # tiles cleared in finished halves (for the score)
    loadouts: list = field(default_factory=list)        # list[Loadout], one per fighter
    log: list = field(default_factory=list)             # crawl-log lines, oldest first
    window_colors: list = field(default_factory=list)   # one color per resolved window
    state: DungeonState = field(init=False)

    def __post_init__(self) -> None:
        if not self.loadouts:
            self.loadouts = [Loadout() for _ in range(self.party_size)]
        if not self.treasury:
            self.treasury = base_treasury(self.party_size)
        self.state = DungeonState(half=self.half, party_size=self.party_size)

    # -- shop --
    def price_multiplier(self) -> float:
        return second_half_multiplier() if self.half == 2 else 1.0

    def catalog(self) -> list:
        return build_catalog(self.pool, self.half, self.price_multiplier())

    def buy(self, member: int, item: Item) -> tuple[bool, str]:
        loadout = self.loadouts[member]
        ok, reason = loadout.can_add(item)
        if not ok:
            return False, reason
        if item.price > self.treasury:
            return False, "not enough gold"
        loadout.add(item)
        self.treasury -= item.price
        return True, ""

    def sell(self, member: int, item_id: str) -> None:
        loadout = self.loadouts[member]
        for it in loadout.items:
            if it.item_id == item_id:
                self.treasury += it.price
                loadout.remove(item_id)
                return

    def set_loadout(self, member: int, item_ids: list) -> list:
        """Rebuild a member's loadout from item_ids -- the leader mirrors what a player bought
        on their own device with their own gold. Structural rules (slot cap, two-handed) are
        enforced; affordability is NOT (the player already paid client-side). Returns ASCII
        notes for any item that could not be placed."""
        catalog_by_id = {it.item_id: it for it in self.catalog()}
        loadout = Loadout()
        notes: list = []
        for item_id in item_ids:
            item = catalog_by_id.get(item_id)
            if item is None:
                notes.append(f"slot {member}: unknown item {item_id}")
                continue
            ok, reason = loadout.can_add(item)
            if ok:
                loadout.add(item)
            else:
                notes.append(f"slot {member}: skipped {item.name} ({reason})")
        self.loadouts[member] = loadout
        return notes

    # -- resolution --
    def party_gear(self) -> PartyGear:
        return PartyGear(
            weapon_bonus=max((l.best_weapon_bonus() for l in self.loadouts), default=0),
            armor_soak=max((l.best_armor_soak() for l in self.loadouts), default=0),
            has_reroll=any(l.has_reroll() for l in self.loadouts),
            consumable_value=sum(it.effect.get("value", 0)
                                 for l in self.loadouts for it in l.items
                                 if it.category == "consumable"))

    def resolve_window(self, fighter_lines: list, actuals: dict,
                       window_label: str) -> WindowResult:
        gear = self.party_gear()
        result = resolve_window(self.rng, self.state, gear, fighter_lines,
                                actuals, window_label)
        self.treasury += result.gold
        self.window_index += 1
        self.window_colors.append(result.color)
        self.log.extend(result.log)
        self._drop_consumables()
        return result

    def _drop_consumables(self) -> None:
        """Consumables persist for one round only; spent or not, they leave after the window."""
        for loadout in self.loadouts:
            for it in list(loadout.items):
                if it.persist == "round":
                    loadout.remove(it.item_id)

    # -- half / score --
    def begin_second_half(self) -> None:
        self.cleared_prev_halves += self.state.depth
        self.half = 2
        self.window_index = 0
        carried_power = self.state.power           # Power is persistent across the game
        self.state = DungeonState(half=2, party_size=self.party_size, power=carried_power)

    def windows_remaining(self) -> int:
        return max(0, _WINDOWS_PER_HALF - self.window_index)

    def half_over(self) -> bool:
        return self.state.finished or self.window_index >= _WINDOWS_PER_HALF

    def match_over(self) -> bool:
        return self.half == 2 and self.half_over()

    def cleared_total(self) -> int:
        return self.cleared_prev_halves + self.state.depth

    def percent(self) -> int:
        return percent_complete(self.cleared_total(), self.party_size)

    def score_label(self) -> str:
        total = total_tiles_game(self.party_size)
        return f"Depth {self.cleared_total()}/{total} ({self.percent()}%)"
