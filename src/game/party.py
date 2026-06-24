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


def _picks_dict(raw: object) -> dict:
    """Coerce the relay's window_picks payload into the expected {slot_str: {...}} shape,
    dropping anything malformed. Party 0 is a long-lived shared test room whose session file
    can hold stale data from an older format; a non-dict payload (or a non-dict entry) must
    never crash a joining client, so we keep only well-formed dict entries."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _actuals_dict(raw: object) -> dict:
    """Coerce the relay's window_actuals payload into {window_str: bundle_dict}, dropping
    anything malformed. Mirrors _picks_dict: a stale shared-room file (party 0) may carry an
    older-format value, and a non-dict payload (or a non-dict bundle) must never crash a
    joining peer. Each kept bundle is the lead's frozen per-window input {actuals, lines, use}."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


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
    seed: Optional[int] = None                          # creator-set RNG seed (peer co-op)
    window_actuals: dict = field(default_factory=dict)  # {window_str: {actuals, lines, use}}

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

    def join_or_restore(self, username: str, max_size: int) -> tuple[Optional[int], bool]:
        """Rejoin-by-username: an existing member keeps their seat; a new member takes the
        next free slot up to max_size. Returns (slot, is_new); (None, False) when full."""
        existing = self.member(username)
        if existing is not None:
            return existing.slot, False
        if len(self.members) >= int(max_size):
            return None, False
        slot = len(self.members)
        self.members.append(Member(username=_norm(username), slot=slot))
        return slot, True

    def all_picks_in(self, window: int) -> bool:
        """True when every member has submitted picks for `window`."""
        return all(
            (entry := self.window_picks.get(str(m.slot))) is not None
            and int(entry.get("w", -1)) == window
            for m in self.members)

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
            "seed": self.seed,
            "window_actuals": {k: dict(v) for k, v in self.window_actuals.items()},
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
            window_picks=_picks_dict(d.get("window_picks", {})),
            seed=(int(d["seed"]) if d.get("seed") not in (None, "") else None),
            window_actuals=_actuals_dict(d.get("window_actuals", {})),
        )


def parse_preds(preds: list) -> dict:
    """["goal:1", "shot:3"] -> {"goal": 1, "shot": 3}. Unknown codes and malformed tokens
    are dropped (picks arrive over the wire)."""
    out: dict = {}
    for token in preds:
        if not isinstance(token, str) or ":" not in token:
            continue
        code, _, raw = token.partition(":")
        if code not in STAT_CODES:
            continue
        try:
            out[code] = int(raw)
        except (TypeError, ValueError):
            continue
    return out


def preds_from_lines(lines: dict) -> list:
    """Inverse of parse_preds: a stable 'code:line' list for every known stat."""
    return [f"{code}:{int(lines.get(code, DEFAULT_LINES[code]))}" for code in STAT_CODES]


def fighter_lines_from_picks(party: "Party", window: int) -> list:
    """One prediction-line dict per member, ordered by slot. A member who has not submitted
    (or submitted partial) picks for `window` is filled from DEFAULT_LINES so the leader can
    always resolve."""
    out: list = []
    for member in sorted(party.members, key=lambda m: m.slot):
        entry = party.window_picks.get(str(member.slot))
        submitted = parse_preds(entry["preds"]) if entry and int(entry.get("w", -1)) == window else {}
        out.append({**DEFAULT_LINES, **submitted})
    return out


def used_consumables_from_picks(party: "Party", window: int) -> list:
    """One list of consumable item_ids per member (ordered by slot) that the member chose to
    USE this window via the predict-screen toggle. Empty for members who did not submit picks
    for `window` (or submitted before the 'use' field existed). Parallel to
    fighter_lines_from_picks so the leader can apply each fighter's potion at resolution."""
    out: list = []
    for member in sorted(party.members, key=lambda m: m.slot):
        entry = party.window_picks.get(str(member.slot))
        if entry and int(entry.get("w", -1)) == window:
            out.append([str(x) for x in entry.get("use", [])])
        else:
            out.append([])
    return out


def split_gold(total: int, n: int) -> list:
    """Split a single gold reward equally among n members; any remainder goes to the lowest
    slots first. split_gold(100, 3) -> [34, 33, 33]."""
    if n <= 0:
        return []
    share, rem = divmod(int(total), n)
    return [share + (1 if i < rem else 0) for i in range(n)]
