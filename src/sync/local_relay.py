# src/sync/local_relay.py
"""In-process party relay: the same async party_* surface as RelayClient, but the whole
party blob lives in this object's memory instead of on the PHP server. No network, no
sockets, no shared state between processes.

Used by the SOLO crawl (a party of one that is always the leader): swapping RelayClient for
LocalRelay removes the entire co-op coordination channel -- the relay round-trips that could
stall, the stale shared session file, the leader/follower reconcile wait -- while keeping the
exact same PartyCoordinator + DungeonPartyFlow code path. Re-enabling co-op is a one-line swap
back to RelayClient.

This is the production promotion of the in-memory FakeRelay the coordinator tests already use,
so its behaviour is covered by tests/test_party_coordinator.py. Pure Python: no pygame."""
import time
from typing import Any, Optional

from src.game.party import Party
from src.utils.constants import CONFIG

_MAX_SIZE = int(CONFIG["party"]["max_size"])


class LocalRelay:
    """Holds one party blob in memory and mutates it exactly as the PHP relay would. The blob
    is created on the first party_join (that caller becomes the leader at slot 0)."""

    def __init__(self) -> None:
        self.blob: Optional[dict] = None

    async def party_join(self, party: int, username: str) -> dict[str, Any]:
        if self.blob is None:
            self.blob = Party.create(party, leader=username).to_dict()
            return {"success": True, "slot": 0, "is_leader": True}
        p = Party.from_dict(self.blob)
        slot, _ = p.join_or_restore(username, max_size=_MAX_SIZE)
        self.blob = p.to_dict()
        return {"success": True, "slot": slot, "is_leader": p.is_leader(username)}

    async def party_state(self, party: int) -> dict[str, Any]:
        # server_time mirrors the PHP relay so PeerCoordinator's staleness gate has a clock.
        return {"success": True, "party": self.blob, "server_time": time.time()}

    async def party_reset(self, party: int) -> dict[str, Any]:
        """Drop the in-memory blob; the next party_join recreates it empty. Mirrors the PHP
        relay's party_reset so the same coordinator code path works in-process."""
        self.blob = None
        return {"success": True}

    async def party_pick(self, party: int, username: str, window: int,
                         preds: list, use: Optional[list] = None) -> dict[str, Any]:
        p = Party.from_dict(self.blob)
        member = p.member(username)
        if member is not None:
            p.window_picks[str(member.slot)] = {
                "w": int(window), "preds": list(preds), "use": list(use or [])}
            self.blob = p.to_dict()
        return {"success": True}

    async def party_loadout(self, party: int, username: str, item_ids: list,
                            treasury: int) -> dict[str, Any]:
        p = Party.from_dict(self.blob)
        member = p.member(username)
        if member is not None:
            member.items, member.treasury, member.ready = list(item_ids), int(treasury), True
            self.blob = p.to_dict()
        return {"success": True}

    async def party_push(self, party: int, username: str,
                         state: dict[str, Any]) -> dict[str, Any]:
        d = dict(self.blob or {})
        state = dict(state)
        if state.pop("clear_picks", False):
            d["window_picks"] = {}
        d.update(state)
        self.blob = d
        return {"success": True}
