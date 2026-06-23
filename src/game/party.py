# src/game/party.py
"""Pure cooperative-party data model: members (each with their own gold pot and loadout),
slots, leader, and the canonical JSON blob the relay stores. Also (added in later tasks) the
per-player gold split and the bridge from each member's submitted picks to the per-fighter
prediction lines the dungeon resolver consumes. Zero pygame, zero relay I/O."""
from dataclasses import dataclass, field
from typing import Optional

from src.utils.constants import CONFIG, load_data

_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
STAT_CODES: list[str] = [s["code"] for s in _STATS]
DEFAULT_LINES: dict[str, int] = {s["code"]: int(s["default_line"]) for s in _STATS}


def _norm(username: str) -> str:
    return username.strip().lower()


def _empty_match() -> dict:
    return {"home": "", "away": "", "home_goals": 0, "away_goals": 0,
            "minute": 0, "status": "NS"}


@dataclass
class Member:
    username: str
    slot: int
    items: list = field(default_factory=list)   # list[str] item_ids (== athlete ids)
    treasury: int = 0                            # this player's own remaining gold
    ready: bool = False                          # finished the current half's shop
    alive: bool = True
    wounds: int = 0

    def to_dict(self) -> dict:
        return {"username": self.username, "slot": self.slot, "items": list(self.items),
                "treasury": self.treasury, "ready": self.ready,
                "alive": self.alive, "wounds": self.wounds}

    @classmethod
    def from_dict(cls, d: dict) -> "Member":
        return cls(username=str(d["username"]), slot=int(d["slot"]),
                   items=list(d.get("items", [])), treasury=int(d.get("treasury", 0)),
                   ready=bool(d.get("ready", False)), alive=bool(d.get("alive", True)),
                   wounds=int(d.get("wounds", 0)))


@dataclass
class Party:
    party_id: int
    leader: str
    phase: str = "lobby"           # lobby -> shop -> play -> done
    half: int = 1
    fixture_id: int = 0
    kickoff_iso: str = ""
    match: dict = field(default_factory=_empty_match)
    pool: list = field(default_factory=list)            # starting-XI rows shared by leader
    members: list = field(default_factory=list)         # list[Member]
    dungeon: Optional[dict] = None                      # DungeonState.to_dict()
    log: list = field(default_factory=list)
    window_colors: list = field(default_factory=list)
    resolved_through_window: int = 0
    window_picks: dict = field(default_factory=dict)    # {slot_str: {"w": int, "preds": [...]}}

    @classmethod
    def create(cls, party_id: int, leader: str) -> "Party":
        lead = _norm(leader)
        return cls(party_id=int(party_id), leader=lead,
                   members=[Member(username=lead, slot=0)])

    def member(self, username: str) -> Optional[Member]:
        u = _norm(username)
        return next((m for m in self.members if _norm(m.username) == u), None)

    def is_leader(self, username: str) -> bool:
        return _norm(username) == self.leader

    def to_dict(self) -> dict:
        return {
            "party_id": self.party_id, "leader": self.leader, "phase": self.phase,
            "half": self.half, "fixture_id": self.fixture_id, "kickoff_iso": self.kickoff_iso,
            "match": dict(self.match), "pool": [dict(r) for r in self.pool],
            "members": [m.to_dict() for m in self.members],
            "dungeon": self.dungeon, "log": list(self.log),
            "window_colors": list(self.window_colors),
            "resolved_through_window": self.resolved_through_window,
            "window_picks": dict(self.window_picks),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Party":
        return cls(
            party_id=int(d["party_id"]), leader=str(d["leader"]),
            phase=str(d.get("phase", "lobby")), half=int(d.get("half", 1)),
            fixture_id=int(d.get("fixture_id", 0)), kickoff_iso=str(d.get("kickoff_iso", "")),
            match={**_empty_match(), **dict(d.get("match", {}))},
            pool=[dict(r) for r in d.get("pool", [])],
            members=[Member.from_dict(m) for m in d.get("members", [])],
            dungeon=d.get("dungeon"), log=list(d.get("log", [])),
            window_colors=list(d.get("window_colors", [])),
            resolved_through_window=int(d.get("resolved_through_window", 0)),
            window_picks=dict(d.get("window_picks", {})),
        )
