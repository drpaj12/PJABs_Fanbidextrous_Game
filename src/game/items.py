# src/game/items.py
"""Generate the shop catalog from the current match's lineup. One item per athlete,
mapped by position; name/price/effect derived from the player and the templates so items
always relate to who is actually playing."""
import hashlib
from dataclasses import dataclass

from src.game.athlete import DraftedAthlete
from src.utils.constants import load_data

_TEMPLATES = load_data("assets/data/item_templates.json")
_POS_CATEGORY = {
    "Attacker": "weapon",
    "Defender": "armor",
    "Midfielder": "consumable",
    "Goalkeeper": "magic",
}
_PERSIST = {"weapon": "infinite", "armor": "infinite",
            "consumable": "round", "magic": "infinite"}


def _stable_index(text: str, n: int) -> int:
    """Deterministic across processes/clients (unlike Python's salted hash())."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % n


def _surname(name: str) -> str:
    parts = name.split()
    return parts[-1] if parts else name


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    category: str
    price: int
    two_handed: bool
    persist: str
    effect: dict
    source_pos: str
    stars: int


def _effect(category: str, stars: int, item_id: str) -> dict:
    t = _TEMPLATES[category]["effect"]
    if category == "magic":
        opts = t["options"]
        return {"kind": "magic", "option": opts[_stable_index("magic:" + item_id, len(opts))]}
    return {"kind": t["kind"], "value": int(t["base"] + t["per_star"] * stars)}


def build_item(athlete: DraftedAthlete, half: int, price_multiplier: float) -> Item:
    category = _POS_CATEGORY.get(athlete.broad_position, "consumable")
    tmpl = _TEMPLATES[category]
    names = tmpl["names"]
    name = names[_stable_index("name:" + athlete.athlete_id, len(names))].format(sur=_surname(athlete.name))
    base_price = tmpl["price"]["base"] + tmpl["price"]["per_star"] * athlete.stars
    return Item(
        item_id=athlete.athlete_id,
        name=name,
        category=category,
        price=int(round(base_price * price_multiplier)),
        two_handed=bool(tmpl.get("two_handed", False)),
        persist=_PERSIST[category],
        effect=_effect(category, athlete.stars, athlete.athlete_id),
        source_pos=athlete.broad_position,
        stars=athlete.stars,
    )


def build_catalog(athletes: list[DraftedAthlete], half: int = 1,
                  price_multiplier: float = 1.0) -> list[Item]:
    return [build_item(a, half, price_multiplier) for a in athletes]
