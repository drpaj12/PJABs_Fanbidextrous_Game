"""
Entities -- the objects your game is made of: tiles, units, pieces,
items, enemies, dice, resources, whatever your game uses.

Replace the Entity example below with whatever fits your DESIGN.md.
Keep all attributes as plain Python data (int, str, list, dict).
No pygame, no images, no screen coordinates here.

The UI layer (src/ui/) is responsible for drawing entities.
This layer is responsible for what they ARE and what they DO.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entity:
    """
    A single object in the game.

    Replace these fields with the attributes from DESIGN.md Section 4.
    Example below uses two generic numeric stats -- rename them to
    whatever your game actually tracks (speed/range, value/weight,
    attack/defense, etc.).
    """
    name: str
    entity_id: str                 # unique identifier, e.g. "entity_01"
    stat_a: int = 0
    stat_b: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)  # e.g. ["starter", "rare"]

    def outranks(self, other: "Entity") -> bool:
        """Example comparison -- replace with your real rule, or delete."""
        return self.stat_a > other.stat_b

    def __repr__(self) -> str:
        return f"Entity({self.name}, a={self.stat_a}, b={self.stat_b})"


@dataclass
class Collection:
    """An ordered group of entities, e.g. one player's hand, inventory, or pool."""
    entities: list[Entity] = field(default_factory=list)

    def draw(self) -> Optional[Entity]:
        """Remove and return the first entity, or None if empty."""
        return self.entities.pop(0) if self.entities else None

    def size(self) -> int:
        return len(self.entities)

    def is_empty(self) -> bool:
        return len(self.entities) == 0


# ------------------------------------------------------------------
# Factory helpers -- load entities from assets/data/entities.json
# ------------------------------------------------------------------

def entity_from_dict(data: dict) -> Entity:
    """Build an Entity from a JSON-loaded dictionary."""
    return Entity(
        name=data["name"],
        entity_id=data["entity_id"],
        stat_a=data.get("stat_a", 0),
        stat_b=data.get("stat_b", 0),
        description=data.get("description", ""),
        tags=data.get("tags", []),
    )
