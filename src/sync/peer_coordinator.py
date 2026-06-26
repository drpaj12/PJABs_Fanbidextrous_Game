# src/sync/peer_coordinator.py
"""Peer-computed cooperative crawl: every client resolves its OWN local CrawlSession from
shared INPUTS, so no client ever hangs waiting on another player. Free of pygame and of any
concrete transport.

How it differs from the leader-authoritative PartyCoordinator
-------------------------------------------------------------
PartyCoordinator makes the leader the single owner of the dungeon: the leader resolves and
PUSHES the dungeon state, followers only read it. That carries three hangs -- the shop
reconcile barrier (wait for all `ready`), SIM `require_all=True` (wait for all picks), and a
dark leader freezing every follower.

PeerCoordinator instead relays INPUTS, not OUTPUT. The creator writes one random `seed` into
the blob once. The api-lead (the creator) polls the match feed and, for each window it
resolves, FREEZES the exact inputs it used -- `{actuals, lines, use}` -- into
`window_actuals[str(window)]`. Every client (lead and followers) then runs the SAME
deterministic `CrawlSession.resolve_window` over that frozen bundle with the shared seed, so
each computes a byte-identical dungeon locally. A follower resolves a window the moment its
bundle appears in the blob; it never waits for the leader to push a result and never waits for
another player's pick (missing picks default via fighter_lines_from_picks -> DEFAULT_LINES,
and the lead already froze them anyway).

So that the existing flow/screen resolution path fires on EVERY client, `is_leader` is forced
True for all peers; a separate `is_api_lead` flag marks the one client that polls the API and
writes the seed / bundles / member economy. `polls_api` exposes that to the flow.

v1 assumptions (documented, accepted for a 3-player game):
- Only the api-lead polls the sports API and shares bundles. If the api-lead goes dark,
  followers pause at the current window (they are waiting on real match data, not on a peer) --
  no hang, but no progress until match data resumes. v2 could let any client poll.
- party_size is frozen when the creator pushes members at shop start; clients added after
  start are not folded into a running resolution (party_size must match across clients for
  determinism)."""
import random
from typing import Optional

from src.game.party import (fighter_lines_from_picks, split_gold,
                            used_consumables_from_picks)
from src.game.score import percent_complete, total_tiles_game
from src.game.staleness import is_blob_stale
from src.sync.party_coordinator import (PartyCoordinator, _MAX_WOUNDS, _PER_PLAYER)
from src.utils.constants import CONFIG

_STALE_MINUTES = int(CONFIG["party"].get("stale_minutes_from_kickoff", 100))


class PeerCoordinator(PartyCoordinator):
    """Every client computes the dungeon locally; the api-lead shares per-window input bundles
    and the creator-set seed. Duck-types PartyCoordinator so DungeonPartyFlow drives it
    unchanged (with `peer`/`is_api_lead` flags routing the API-poll gates)."""

    def __init__(self, relay, party_id: int, username: str, pool: list,
                 actuals_fn, seed: Optional[int] = None) -> None:
        super().__init__(relay, party_id, username, pool, actuals_fn, seed=seed)
        # Remember whether the caller pinned a seed. If not, the creator mints a random one at
        # join so different sessions diverge; followers always adopt the blob's seed.
        self._explicit_seed: Optional[int] = seed
        self.is_api_lead: bool = False
        self._resolved_through: int = 0   # windows resolved locally in the CURRENT half
        # The fixture THIS client is about to start. Set by the flow on the api-lead path only
        # (a follower does not choose a game). Feeds the staleness gate: a blob frozen on a
        # different fixture is leftover from a previous game and gets wiped on join.
        self.chosen_fixture_id: Optional[int] = None
        self.stale_minutes: int = _STALE_MINUTES

    # -- identity / read -----------------------------------------------------

    @property
    def polls_api(self) -> bool:
        """The api-lead (creator) is the only client that fetches the match feed and writes
        the seed / per-window bundles / member economy into the blob."""
        return self.is_api_lead

    def _blob_is_stale(self) -> bool:
        """True when the blob we just read is leftover from an earlier game: a different chosen
        fixture (api-lead only -- it sets chosen_fixture_id) or a game whose kickoff is older
        than stale_minutes by the relay clock. A lobby blob (fixture 0, no kickoff) is never
        stale. server_time None (relay reported no clock) disables the age signal."""
        if self.party is None:
            return False
        return is_blob_stale(
            blob_fixture_id=self.party.fixture_id,
            kickoff_iso=self.party.kickoff_iso,
            server_time=self.server_time,
            stale_minutes=self.stale_minutes,
            chosen_fixture_id=self.chosen_fixture_id)

    async def join(self) -> None:
        await super().join()
        # The relay's is_leader (creator at slot 0) becomes our api-lead. Then force is_leader
        # True for ALL peers so the flow's resolution path runs locally on every client.
        self.is_api_lead = bool(self.is_leader)
        self.is_leader = True
        if self.is_api_lead:
            # Auto-clear: if we rejoined onto a stale blob (a different fixture, or a game long
            # over), wipe the server state and rejoin a fresh empty blob so this game never
            # inherits a previous game's dungeon/log/bundles.
            if self._blob_is_stale():
                await self.relay.party_reset(self.party_id)
                await super().join()
            if self._explicit_seed is None:
                self.seed = random.randrange(1, 1_000_000)
            await self.relay.party_push(self.party_id, self.username,
                                        {"seed": self.seed, "window_actuals": {}})
            await self.refresh()
        else:
            self._adopt_seed()

    async def refresh(self) -> None:
        await super().refresh()
        self._adopt_seed()

    def _adopt_seed(self) -> None:
        """Followers (and a re-reading lead) take the creator's seed from the blob so every
        client's CrawlSession shares one RNG stream."""
        if self.party is not None and self.party.seed is not None:
            self.seed = int(self.party.seed)

    def resolved_through(self) -> int:
        """LOCAL resolved-window count for the current half (each peer advances its own)."""
        return self._resolved_through

    # -- shop / start --------------------------------------------------------

    async def leader_start(self) -> None:
        """Creator only: seed each member's treasury and flip lobby -> shop, writing the seed
        and clearing ALL prior-game state. Followers do not push; their lobby auto-advances when
        they read phase == 'shop'.

        The clear is exhaustive on purpose: besides window_actuals it also resets dungeon, log,
        window_colors, resolved_through_window and window_picks. Leaving any of these from a
        previous game on the same party number was the source of corrupted co-op state -- a new
        game would render an old dungeon/log until the first window resolved over it."""
        if not self.is_api_lead:
            return
        await self.refresh()
        if self.party is None:
            return
        members = []
        for m in self.party.members:
            d = m.to_dict()
            d["treasury"] = _PER_PLAYER
            d["ready"] = False
            members.append(d)
        await self.relay.party_push(self.party_id, self.username, {
            "phase": "shop", "half": 1, "members": members, "seed": self.seed,
            "window_actuals": {}, "dungeon": None, "log": [], "window_colors": [],
            "resolved_through_window": 0, "clear_picks": True})
        await self.refresh()

    async def leader_try_reconcile_shop(self) -> bool:
        """No barrier: a peer proceeds to play the instant IT has shopped, never waiting on
        other players' `ready` flags. Build the local session and apply every loadout known so
        far (re-applied at each resolve, so a late-arriving loadout still lands). Returns True
        unconditionally; pushes nothing (no shared 'play' phase in the peer model)."""
        await self.refresh()
        if self.party is None:
            return False
        self._build_session()
        self._apply_loadouts()
        return True

    def _apply_loadouts(self) -> None:
        """Mirror every member's bought items onto the local session, by slot. Idempotent:
        set_loadout rebuilds the loadout from scratch, so calling it again with a member's
        latest items simply refreshes it."""
        if self.session is None or self.party is None:
            return
        for m in sorted(self.party.members, key=lambda x: x.slot):
            if m.slot < len(self.session.loadouts):
                self.session.set_loadout(m.slot, m.items)

    # -- resolution (every client, locally) ----------------------------------

    def _resolution_input(self, window: int) -> Optional[dict]:
        """The frozen per-window input bundle {actuals, lines, use}.

        api-lead: compute it now from the live feed + the picks/loadouts in the blob, so it can
        be shared verbatim. follower: read the lead's already-shared bundle from the blob, or
        None when it has not arrived yet (-> this client is not ready to resolve the window)."""
        if self.is_api_lead:
            return {
                "actuals": dict(self.actuals_fn(window)),
                "lines": fighter_lines_from_picks(self.party, window),
                "use": used_consumables_from_picks(self.party, window),
            }
        # Follower: never replay bundles from a stale blob (a game long over by the relay
        # clock). Treat them as not-yet-available so this client waits for fresh state instead
        # of resurrecting a finished game's dungeon.
        if self._blob_is_stale():
            return None
        bundle = self.party.window_actuals.get(str(window)) if self.party else None
        if not isinstance(bundle, dict) or "actuals" not in bundle:
            return None
        return {
            "actuals": dict(bundle.get("actuals", {})),
            "lines": [dict(line) for line in bundle.get("lines", [])],
            "use": [list(u) for u in bundle.get("use", [])],
        }

    async def leader_try_resolve(self, window: int, require_all: bool = False) -> bool:
        """Resolve one window on THIS client's local session. `require_all` is ignored -- the
        peer model never blocks on other players (the lead already froze the inputs, and any
        missing pick defaults). Returns True on success, False when the window is already
        resolved locally or its bundle is not yet available."""
        if window <= self._resolved_through:
            return False
        self._build_session()
        bundle = self._resolution_input(window)
        if bundle is None:
            return False
        self._apply_loadouts()
        label = f"H{self.session.half} W{window}"
        result = self.session.resolve_window(
            bundle["lines"], bundle["actuals"], label, used_consumables=bundle["use"])
        self.last_gold = result.gold
        self.last_actuals = dict(bundle["actuals"])
        self._resolved_through = window
        if self.is_api_lead:
            await self._push_after_resolve(window, bundle)
        return True

    async def leader_catch_up(self, through_window: int) -> int:
        """Fast-forward: resolve every still-unresolved window up to `through_window` whose
        bundle is available. The flow bounds `through_window` to what the api-lead's feed
        covers, or (for a follower) to the count of bundles already in the blob."""
        w = self._resolved_through + 1
        while w <= through_window:
            if not await self.leader_try_resolve(w, require_all=False):
                break
            w += 1
        return self._resolved_through

    async def leader_advance_half(self) -> None:
        """Advance the LOCAL session to half 2 (or close the match). Every peer advances its
        own session and resets its local resolved counter; only the api-lead writes the shared
        phase/half/economy and clears the stale H1 bundles so H2 windows gate fresh."""
        if self.session is None:
            return
        if self.session.half == 1:
            self.session.begin_second_half()
            self._resolved_through = 0
            if self.is_api_lead:
                members = []
                for m in self.party.members:
                    d = m.to_dict()
                    d["ready"] = False
                    d["treasury"] = max(int(m.treasury), _PER_PLAYER)
                    members.append(d)
                await self.relay.party_push(self.party_id, self.username, {
                    "phase": "shop", "half": 2, "resolved_through_window": 0,
                    "members": members, "clear_picks": True, "window_actuals": {}})
        elif self.is_api_lead:
            await self.relay.party_push(self.party_id, self.username, {"phase": "done"})
        await self.refresh()

    # -- view (from the LOCAL session, not a pushed dungeon) ------------------

    def view(self) -> dict:
        p = self.party
        size = len(p.members) if p else 1
        s = self.session
        if s is None:
            depth = power = wounds = threat = 0
            cleared_total = 0
            log: list = []
            colors: list = []
        else:
            depth = s.state.depth
            power = s.state.power
            wounds = s.state.wounds
            threat = s.state.threat
            cleared_total = s.cleared_total()
            log = list(s.log)
            colors = list(s.window_colors)
        return {
            "depth": depth,
            "total": int(total_tiles_game(size)),
            "power": power,
            "wounds": wounds,
            "threat": threat,
            "actuals": dict(self.last_actuals),
            "log": log,
            "window_colors": colors,
            "members": [(m.username, m.treasury) for m in p.members] if p else [],
            "match": dict(p.match) if p else {},
            "percent": percent_complete(cleared_total, size) if s is not None else 0,
        }

    # -- internals -----------------------------------------------------------

    async def _push_after_resolve(self, window: int, bundle: Optional[dict] = None) -> None:
        """api-lead only: share the frozen input `bundle` for this window plus the member
        economy (gold split, wounds, deployed-consumable removal) and a display copy of the
        dungeon. Unlike the leader-authoritative push this NEVER clears window_picks -- a
        follower that has not yet resolved the window must still find the inputs -- and it adds
        the bundle to window_actuals so followers can replay it for a byte-identical result."""
        if not self.is_api_lead:
            return
        s = self.session
        shares = split_gold(self.last_gold, len(self.party.members))
        used_sets = (bundle or {}).get("use", []) or []
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
        merged_actuals = dict(self.party.window_actuals)
        if bundle is not None:
            merged_actuals[str(window)] = bundle
        dungeon_payload = {**s.state.to_dict(), "cleared_prev": s.cleared_prev_halves,
                           "actuals": dict(self.last_actuals)}
        await self.relay.party_push(self.party_id, self.username, {
            "dungeon": dungeon_payload, "log": list(s.log),
            "window_colors": list(s.window_colors), "members": members,
            "resolved_through_window": window, "window_actuals": merged_actuals})
        await self.refresh()
