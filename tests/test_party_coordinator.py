import asyncio

from src.game.athlete import DraftedAthlete
from src.game.party import Party
from src.sync.party_coordinator import PartyCoordinator


class FakeRelay:
    """In-memory stand-in for RelayClient with the same async party_* surface."""
    def __init__(self):
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

    async def party_pick(self, party, username, window, preds):
        p = Party.from_dict(self.blob)
        p.window_picks[str(p.member(username).slot)] = {"w": window, "preds": preds}
        self.blob = p.to_dict()
        return {"success": True}

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


def _pool(n=22):
    cats = ["Attacker", "Defender", "Midfielder", "Goalkeeper"]
    # athlete_id must be str (DraftedAthlete.create hashes "arch:" + athlete_id)
    return [DraftedAthlete.create(athlete_id=str(i), name=f"P{i}", broad_position=cats[i % 4],
            team="T", jersey=i) for i in range(1, n + 1)]


def _actuals(_w):
    return {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}


def _coord(relay, username, pool):
    return PartyCoordinator(relay=relay, party_id=0, username=username,
                            pool=pool, actuals_fn=_actuals)


def _join_all(*coords):
    for c in coords:
        asyncio.run(c.join())


def test_join_assigns_leader_and_seeds_starting_gold_on_shop():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    assert lead.is_leader and not a.is_leader
    asyncio.run(lead.leader_start())            # lobby -> shop, seed each pot
    asyncio.run(a.refresh())
    assert a.shop_budget() == 300 and lead.shop_budget() == 300


def test_full_window_round_trip_resolves_and_followers_see_depth():
    relay, pool = FakeRelay(), _pool()
    lead, a, b = (_coord(relay, "drpaj", pool), _coord(relay, "alice", pool),
                  _coord(relay, "bob", pool))
    _join_all(lead, a, b)
    asyncio.run(lead.leader_start())
    for c in (lead, a, b):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, a, b):
        asyncio.run(c.refresh())
    assert lead.phase() == "play" and a.phase() == "play"
    assert lead.session.party_size == 3
    for c in (lead, a, b):
        asyncio.run(c.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    for c in (a, b):
        asyncio.run(c.refresh())
    assert lead.resolved_through() == 1 and b.resolved_through() == 1
    assert b.view()["depth"] > 0 and b.view()["depth"] == lead.view()["depth"]


def test_window_gold_is_split_into_each_players_pot():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    asyncio.run(a.refresh())
    # each player's pot grew by an equal share of the window gold
    assert a.my_treasury() >= 300 and lead.my_treasury() >= 300
    assert (a.my_treasury() - 300) + (lead.my_treasury() - 300) == lead.last_gold


def test_leader_resolves_with_force_when_a_follower_did_not_submit():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(lead.refresh())
    asyncio.run(lead.submit_pick(1, {"goal": 1}))    # only the leader submitted
    asyncio.run(lead.refresh())
    assert asyncio.run(lead.leader_try_resolve(1, require_all=True)) is False   # blocked
    assert asyncio.run(lead.leader_try_resolve(1, require_all=False)) is True   # forced
    assert lead.resolved_through() == 1
