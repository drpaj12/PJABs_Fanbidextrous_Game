# src/game/loadout.py
"""A single fighter's loadout: up to loadout_size items, at most one two-handed weapon,
extra-slot magic raises the cap. Exposes the combat bonuses the dungeon resolver needs."""
from dataclasses import dataclass, field

from src.game.items import Item
from src.utils.constants import CONFIG

_BASE_CAP = int(CONFIG["game"]["loadout_size"])


@dataclass
class Loadout:
    items: list = field(default_factory=list)

    def slot_cap(self) -> int:
        extra = sum(1 for it in self.items
                    if it.category == "magic" and it.effect.get("option") == "extra_slot")
        return _BASE_CAP + extra

    def has_weapon(self) -> bool:
        return any(it.category == "weapon" for it in self.items)

    def can_add(self, item: Item) -> tuple[bool, str]:
        if any(it.item_id == item.item_id for it in self.items):
            return False, "already owned"
        if item.category == "weapon" and item.two_handed and self.has_weapon():
            return False, "only one two-handed weapon"
        if item.category == "armor" and item.armor_slot and any(
                it.armor_slot == item.armor_slot for it in self.items):
            return False, "armor slot already filled"
        if len(self.items) >= self.slot_cap():
            return False, "no free slot"
        return True, ""

    def add(self, item: Item) -> None:
        ok, reason = self.can_add(item)
        if not ok:
            raise ValueError(reason)
        self.items.append(item)

    def remove(self, item_id: str) -> None:
        self.items = [it for it in self.items if it.item_id != item_id]

    def total_cost(self) -> int:
        return sum(it.price for it in self.items)

    def best_weapon_bonus(self) -> int:
        vals = [it.effect.get("value", 0) for it in self.items if it.category == "weapon"]
        return max(vals) if vals else 0

    def best_armor_soak(self) -> int:
        vals = [it.effect.get("value", 0) for it in self.items if it.category == "armor"]
        return max(vals) if vals else 0

    def has_reroll(self) -> bool:
        return any(it.category == "magic" and it.effect.get("option") == "reroll"
                   for it in self.items)
