# src/sync/party_coordinator.py
"""Leader-authoritative party sync + per-player economy, free of pygame and of any concrete
transport.

Every client constructs one PartyCoordinator. All clients submit their own loadout (bought
with their own gold pot) and per-window picks; the LEADER alone holds the authoritative
CrawlSession, reconciles the shop, resolves each window, splits the gold reward equally into
each player's pot, and pushes the canonical dungeon state (plus the live match summary and
lineup pool). Followers only read (refresh) and render (view).

The relay object needs only the async party_* methods (RelayClient in production, an in-memory
fake in tests). actuals_fn(window) -> per-window actuals dict is supplied by the flow (built
from the recorded feed in SIM, the live feed in LIVE)."""
import random
from typing import Callable, Optional

from src.game.crawl import CrawlSession
from src.game.party import (Party, fighter_lines_from_picks, preds_from_lines, split_gold,
                            used_consumables_from_picks)
from src.game.score import percent_complete, total_tiles_game
from src.utils.constants import CONFIG

_PARTY = CONFIG["party"]
_MAX_SIZE = int(_PARTY["max_size"])
_PER_PLAYER = int(_PARTY["per_player_treasury"])
_MAX_WOUNDS = int(CONFIG["dungeon"]["max_wounds"])


class PartyCoordinator:
    def __init__(self, relay, party_id: int, username: str, pool: list,
                 actuals_fn: Callable[[int], dict], seed: Optional[int] = None) -> None:
        self.relay = relay
        self.party_id = int(party_id)
        self.username = username
        self.pool = pool
        self.actuals_fn = actuals_fn
        self.seed = int(seed if seed is not None else CONFIG["game"]["rng_seed"])
        self.slot: int = -1
        self.is_leader: bool = False
        self.party: Optional[Party] = None
        self.session: Optional[CrawlSession] = None   # authoritative, leader only
        self.last_gold: int = 0                       # gold from the most recent resolution
        self.last_actuals: dict = {}                  # actuals of the most recent resolution

    # -- identity / read -----------------------------------------------------

    async def join(self) -> None:
        resp = await self.relay.party_join(self.party_id, self.username)
        self.slot = int(resp.get("slot", -1))
        self.is_leader = bool(resp.get("is_leader", False))
        await self.refresh()

    async def refresh(self) -> None:
        resp = await self.relay.party_state(self.party_id)
        blob = resp.get("party")
        if blob:
            self.party = Party.from_dict(blob)

    @property
    def polls_api(self) -> bool:
        """Whether THIS client fetches the match feed and shares it. In the leader-authoritative
        model that is the leader; PeerCoordinator overrides it to the separate api-lead flag.
        The live flow gates its sports-API polling on this so both coordinators share one path."""
        return self.is_leader

    def phase(self) -> str:
        return self.party.phase if self.party else "lobby"

    def half(self) -> int:
        return self.party.half if self.party else 1

    def resolved_through(self) -> int:
        return self.party.resolved_through_window if self.party else 0

    def me(self) -> Optional[object]:
        return self.party.member(self.username) if self.party else None

    def my_treasury(self) -> int:
        m = self.me()
        return m.treasury if m else 0

    def shop_budget(self) -> int:
        return self.my_treasury()

    def view(self) -> dict:
        p = self.party
        d = (p.dungeon if p and p.dungeon else {})
        size = len(p.members) if p else 1
        # cleared_prev is written into the dungeon blob by the leader at every
        # _push_after_resolve so followers have the correct H1 depth when computing
        # H2 percent. Fall back to the local session (leader path) or 0 (pre-resolve).
        cleared_prev = int(d.get("cleared_prev",
                                 self.session.cleared_prev_halves if self.session else 0))
        depth = int(d.get("depth", 0))
        return {
            "depth": depth,
            "total": int(total_tiles_game(size)),
            "power": int(d.get("power", 0)),
            "wounds": int(d.get("wounds", 0)),
            "threat": int(d.get("threat", 0)),
            "actuals": dict(d.get("actuals", {})),
            "log": list(p.log if p else []),
            "window_colors": list(p.window_colors if p else []),
            "members": [(m.username, m.treasury) for m in p.members] if p else [],
            "match": dict(p.match) if p else {},
            "percent": percent_complete(depth + cleared_prev, size) if p else 0,
        }

    # -- member writes -------------------------------------------------------

    async def submit_loadout(self, item_ids: list, treasury: int) -> None:
        await self.relay.party_loadout(self.party_id, self.username, item_ids, int(treasury))

    async def submit_pick(self, window: int, lines: dict,
                          use: Optional[list] = None) -> None:
        """Submit this player's picks for `window`. `use` is the list of consumable item_ids
        the player toggled to deploy this window (empty = hold them in inventory)."""
        await self.relay.party_pick(self.party_id, self.username, window,
                                    preds_from_lines(lines), use=list(use or []))

    # -- leader-authoritative actions ----------------------------------------

    async def leader_start(self) -> None:
        """Transition from lobby -> shop, seeding each member's treasury to _PER_PLAYER."""
        if not self.is_leader:
            return
        # Always fetch the latest blob first so we seed ALL members who have joined,
        # not just those present when this coordinator last refreshed.
        await self.refresh()
        if self.party is None:
            return
        # INVARIANT: members[] is a whole-array replace on the relay (the PHP party_push
        # overwrites the entire members key, not individual slots). The leader must only
        # push members at a phase boundary where followers are idle on member fields.
        # Here that is safe: this push also flips phase from lobby -> shop, so followers
        # have not yet started writing their loadout/treasury/ready fields. Pushing members
        # mid-shop would clobber a follower's in-flight loadout submission.
        members = []
        for m in self.party.members:
            d = m.to_dict()
            d["treasury"] = _PER_PLAYER
            d["ready"] = False
            members.append(d)
        await self.relay.party_push(self.party_id, self.username,
                                    {"phase": "shop", "members": members})
        await self.refresh()

    async def leader_try_reconcile_shop(self) -> bool:
        """When all members are ready, build the session and advance phase to play.
        Returns True if the shop was reconciled, False if any member is still shopping."""
        if not self.is_leader:
            return False
        # Fetch latest state so we see every member's current ready flag before deciding.
        await self.refresh()
        if self.party is None or self.party.phase != "shop":
            return False
        if not all(m.ready for m in self.party.members):
            return False
        self._build_session()
        for m in sorted(self.party.members, key=lambda x: x.slot):
            self.session.set_loadout(m.slot, m.items)
        await self.relay.party_push(self.party_id, self.username, {"phase": "play"})
        await self.refresh()
        return True

    async def leader_try_resolve(self, window: int, require_all: bool = True) -> bool:
        """Resolve one window.

        If require_all=True (default), blocks and returns False when any member has not yet
        submitted picks for this window. If require_all=False, forces resolution using
        DEFAULT_LINES for any missing pick. Returns True on success."""
        if not self.is_leader or self.party is None or self.party.phase != "play":
            return False
        if self.party.resolved_through_window >= window:
            return False
        if require_all and not self.party.all_picks_in(window):
            return False
        self._build_session()
        fighter_lines = fighter_lines_from_picks(self.party, window)
        used = used_consumables_from_picks(self.party, window)
        label = f"H{self.session.half} W{window}"
        actuals = self.actuals_fn(window)
        result = self.session.resolve_window(fighter_lines, actuals, label,
                                             used_consumables=used)
        self.last_gold = result.gold
        self.last_actuals = dict(actuals)
        await self._push_after_resolve(window, used)
        return True

    async def leader_catch_up(self, through_window: int) -> int:
        """Fast-forward the live crawl: resolve every still-unresolved window up to and
        including `through_window`, forcing defaults for any pick a member never submitted
        (require_all=False). Used when a client enters a live match that has already played
        past windows -- those windows auto-resolve so the player lands on the current live
        window. Leader only; a follower call is a no-op. Returns the new resolved_through."""
        if not self.is_leader:
            return self.resolved_through()
        w = self.resolved_through() + 1
        while w <= through_window:
            if not await self.leader_try_resolve(w, require_all=False):
                break
            w += 1
        return self.resolved_through()

    async def leader_advance_half(self) -> None:
        """Move from half 1 -> half 2 shop, or close out the match."""
        if not self.is_leader or self.session is None:
            return
        if self.session.half == 1:
            self.session.begin_second_half()
            # Safe to push members here (see INVARIANT note in leader_start): the phase
            # flips to shop simultaneously, so followers are not writing member fields.
            members = []
            for m in self.party.members:
                d = m.to_dict()
                d["ready"] = False
                # Auto-grant the per-player second-half allowance: top each pot up to
                # _PER_PLAYER so every player can re-shop in H2 even after auto fast-forward
                # spent/earned little. Never reduces a pot that carried more gold from H1.
                d["treasury"] = max(int(m.treasury), _PER_PLAYER)
                members.append(d)
            await self.relay.party_push(self.party_id, self.username, {
                "phase": "shop", "half": 2, "resolved_through_window": 0,
                "members": members, "clear_picks": True})
        else:
            await self.relay.party_push(self.party_id, self.username, {"phase": "done"})
        await self.refresh()

    async def leader_share_match(self, match: dict, pool_rows: Optional[list] = None,
                                 fixture_id: Optional[int] = None,
                                 kickoff_iso: Optional[str] = None) -> None:
        """Push live match data (scoreline, status) and optionally the lineup pool."""
        if not self.is_leader or self.party is None:
            return
        state: dict = {"match": match}
        if pool_rows is not None:
            state["pool"] = pool_rows
        if fixture_id is not None:
            state["fixture_id"] = int(fixture_id)
        if kickoff_iso is not None:
            state["kickoff_iso"] = kickoff_iso
        await self.relay.party_push(self.party_id, self.username, state)
        await self.refresh()

    # -- internals -----------------------------------------------------------

    def _build_session(self) -> None:
        """Create the CrawlSession once; idempotent on subsequent calls."""
        if self.session is None:
            self.session = CrawlSession(party_size=len(self.party.members),
                                        pool=self.pool, rng=random.Random(self.seed))

    async def _push_after_resolve(self, window: int,
                                  used_consumables: Optional[list] = None) -> None:
        """Push the authoritative post-resolve state: dungeon, log, window_colors, each
        member's updated treasury share, and a flag to clear the now-stale window_picks.
        Consumables a member deployed this window are stripped from their pushed inventory so
        followers see the potion gone."""
        s = self.session
        shares = split_gold(self.last_gold, len(self.party.members))
        used_sets = used_consumables or []
        # Safe to push members here (see INVARIANT note in leader_start): resolve runs
        # during play phase when followers write only window_picks, not member fields.
        members = []
        for m in sorted(self.party.members, key=lambda x: x.slot):
            d = m.to_dict()
            spent = set(used_sets[m.slot]) if m.slot < len(used_sets) else set()
            if spent:
                d["items"] = [i for i in d["items"] if i not in spent]
            d["treasury"] = m.treasury + shares[m.slot]
            d["wounds"] = s.state.wounds
            d["alive"] = s.state.wounds < _MAX_WOUNDS
            members.append(d)
        # cleared_prev is included so followers can compute the correct H2 percent.
        # DungeonState.from_dict ignores unknown keys, so the extra field is safe.
        dungeon_payload = {**s.state.to_dict(), "cleared_prev": s.cleared_prev_halves,
                           "actuals": dict(self.last_actuals)}
        await self.relay.party_push(self.party_id, self.username, {
            "dungeon": dungeon_payload, "log": list(s.log),
            "window_colors": list(s.window_colors), "members": members,
            "resolved_through_window": window, "clear_picks": True})
        await self.refresh()
