# TOOLS/smoke_party_live.py
"""Headless construct smoke for the LIVE cooperative party flow (Task 14 fix).

Exercises, with NO display and NO network (FakeRelay + a stub LiveFeed):
  1. LEADER feed-share path: the leader publishes fixture_id + lineup pool + match into the
     shared blob BEFORE the lobby flips to shop, then builds its CrawlSession pool from the feed.
  2. FOLLOWER from-blob path: a second (non-lead) client joins the same party with an EMPTY pool,
     never touches the fixture picker / sports API, and rebuilds its draft pool + live machinery
     from the leader's shared blob, reaching the shop.
  3. HALF-2 clock re-anchor: the party clock is rebuilt with start_minute=45 for the second half
     (mirrors LiveFlow.launch_half(2)).

Run:  .venv/Scripts/python TOOLS/smoke_party_live.py
ASCII-only output. Uses the SDL dummy driver so it needs no display."""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.game.party import Party  # noqa: E402
from src.sync.party_coordinator import PartyCoordinator  # noqa: E402
from src.ui.app import App  # noqa: E402
from src.ui.sim import SimMode  # noqa: E402
from src.ui.flow import DungeonPartyFlow, _HALF_MIN, _WINDOW_MIN  # noqa: E402
from src.game.half_clock import HalfClock  # noqa: E402


class FakeRelay:
    """In-memory stand-in for RelayClient (same async party_* surface as the unit tests)."""
    def __init__(self) -> None:
        self.blob = None

    async def party_join(self, party, username):
        if self.blob is None:
            self.blob = Party.create(party, leader=username).to_dict()
            return {"success": True, "slot": 0, "is_leader": True}
        p = Party.from_dict(self.blob)
        slot, _ = p.join_or_restore(username, max_size=3)
        self.blob = p.to_dict()
        return {"success": True, "slot": slot, "is_leader": p.is_leader(username)}

    async def party_state(self, party):
        return {"success": True, "party": self.blob}

    async def party_loadout(self, party, username, item_ids, treasury):
        p = Party.from_dict(self.blob)
        m = p.member(username)
        m.items, m.treasury, m.ready = item_ids, treasury, True
        self.blob = p.to_dict()
        return {"success": True}

    async def party_push(self, party, username, state):
        d = dict(self.blob)
        if state.pop("clear_picks", False):
            d["window_picks"] = {}
        d.update(state)
        self.blob = d
        return {"success": True}


class StubLiveFeed:
    """Minimal LiveFeed stand-in: exposes only the accessors the LIVE leader share path uses."""
    def __init__(self, rows) -> None:
        self._rows = rows

    def has_lineups(self) -> bool:
        return bool(self._rows)

    def lineups(self) -> list:
        return list(self._rows)

    def home_team(self) -> str:
        return "Netherlands"

    def away_team(self) -> str:
        return "Sweden"

    def home_goals(self) -> int:
        return 1

    def away_goals(self) -> int:
        return 0

    def current_minute(self) -> int:
        return 30

    def status_short(self) -> str:
        return "1H"

    def kickoff_iso(self):
        return "2026-06-20T17:00:00+00:00"


class RecordingApp(App):
    """Real App (dummy SDL surface) that also records every set_screen target by type name."""
    def __init__(self) -> None:
        super().__init__()
        self.screens: list = []

    def set_screen(self, screen) -> None:
        self.screens.append(type(screen).__name__)
        super().set_screen(screen)


def _lineup_rows(n: int = 22) -> list:
    cats = ["Attacker", "Defender", "Midfielder", "Goalkeeper"]
    return [{"athlete_id": str(i), "name": f"P{i}", "broad_position": cats[i % 4],
             "team": "T", "jersey": i} for i in range(1, n + 1)]


def main() -> None:
    rows = _lineup_rows()
    relay = FakeRelay()
    sim = SimMode(False)

    # -- LEADER feed-share path --------------------------------------------
    lead_app = RecordingApp()
    lead_coord = PartyCoordinator(relay=relay, party_id=0, username="drpaj",
                                  pool=[], actuals_fn=lambda w: {})
    asyncio.run(lead_coord.join())
    assert lead_coord.is_leader, "FAIL leader did not get leader slot"
    lead_pool = [type("A", (), {"athlete_id": r["athlete_id"]})() for r in rows]
    lead_flow = DungeonPartyFlow(lead_app, StubLiveFeed(rows), lead_pool, lead_coord, sim)
    lead_flow.kickoff_epoch = 0.0
    lead_flow.attach_live(None, StubLiveFeed(rows), 1539007,
                          HalfClock(_HALF_MIN, _WINDOW_MIN))
    asyncio.run(lead_flow._leader_share_then_start())
    asyncio.run(lead_coord.refresh())
    assert lead_coord.party.fixture_id == 1539007, "FAIL fixture_id not shared"
    assert len(lead_coord.party.pool) == len(rows), "FAIL pool not shared into blob"
    assert lead_coord.party.match.get("home") == "Netherlands", "FAIL match not shared"
    assert lead_coord.phase() == "shop", "FAIL leader did not flip lobby -> shop"
    print(f"OK leader shared fixture={lead_coord.party.fixture_id} "
          f"pool={len(lead_coord.party.pool)} match={lead_coord.party.match['home']} "
          f"v {lead_coord.party.match['away']}; phase={lead_coord.phase()}")

    # -- FOLLOWER from-blob path -------------------------------------------
    fol_app = RecordingApp()
    fol_coord = PartyCoordinator(relay=relay, party_id=0, username="alice",
                                 pool=[], actuals_fn=lambda w: {})
    asyncio.run(fol_coord.join())
    assert not fol_coord.is_leader, "FAIL follower wrongly got leader"
    # Follower flow: EMPTY pool, placeholder feed, no fixture picker ever constructed.
    fol_flow = DungeonPartyFlow(fol_app, StubLiveFeed([]), [], fol_coord, sim)
    fol_flow.feed_client = None          # FeedClient(is_lead=False) in production; unused here
    fol_flow.is_follower_live = True
    asyncio.run(fol_coord.refresh())     # pull the leader's shared blob
    assert fol_coord.party.fixture_id == 1539007, "FAIL follower cannot read shared fixture"
    assert len(fol_coord.party.pool) == len(rows), "FAIL follower cannot read shared pool"
    # Build live machinery + pool purely from the blob, then enter the shop.
    attached = fol_flow.attach_live_from_blob()
    fol_flow._sync_pool_from_blob()
    assert attached and fol_flow.live, "FAIL follower did not attach live from blob"
    assert fol_flow.fixture_id == 1539007, "FAIL follower attached wrong fixture"
    assert len(fol_flow.pool) == len(rows), "FAIL follower pool not rebuilt from blob rows"
    fol_flow._to_shop()
    assert "ShopScreen" in fol_app.screens, "FAIL follower did not reach shop"
    # The follower must NEVER have built a fixture picker / resolve / lineup-wait screen.
    forbidden = {"FixtureSelectScreen", "LiveResolveScreen", "LiveWaitScreen"}
    assert not (forbidden & set(fol_app.screens)), \
        f"FAIL follower built a picker screen: {fol_app.screens}"
    print(f"OK follower read blob fixture+pool and reached {fol_app.screens[-1]} "
          f"with {len(fol_flow.pool)} athletes; no picker screens "
          f"({sorted(set(fol_app.screens))})")

    # -- HALF-2 clock re-anchor --------------------------------------------
    before = fol_flow.clock.start_minute
    fol_flow._reanchor_half_two()
    after = fol_flow.clock.start_minute
    assert before == 0 and after == _HALF_MIN, \
        f"FAIL half-2 clock not re-anchored: {before} -> {after}"
    # Half-2 windows must now read absolute minutes 45..90, not 0..45.
    assert fol_flow.clock.window_start(1) == _HALF_MIN, "FAIL half-2 window_start wrong"
    print(f"OK half-2 clock re-anchored: start_minute {before} -> {after}; "
          f"window 1 start = {fol_flow.clock.window_start(1)}'")

    print("OK smoke complete")


if __name__ == "__main__":
    main()
