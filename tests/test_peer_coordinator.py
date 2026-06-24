"""Peer-computed co-op: every client resolves its own local CrawlSession from the creator-set
seed + the api-lead's frozen per-window input bundles. These tests prove the no-hang
properties -- byte-identical local results across clients, resolution from the shared bundle
even when a follower never submitted its pick, no shop reconcile barrier, and a clean half
advance -- using the production in-process LocalRelay as the shared bulletin board."""
import asyncio

from src.game.athlete import DraftedAthlete
from src.sync.local_relay import LocalRelay
from src.sync.peer_coordinator import PeerCoordinator


def _pool(n=22):
    cats = ["Attacker", "Defender", "Midfielder", "Goalkeeper"]
    return [DraftedAthlete.create(athlete_id=str(i), name=f"P{i}", broad_position=cats[i % 4],
            team="T", jersey=i) for i in range(1, n + 1)]


def _actuals(window):
    # Deterministic, window-varying actuals so successive windows differ (proves the RNG +
    # state advance the same way on both clients, not just a single repeated outcome).
    base = {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}
    return {k: v + window for k, v in base.items()}


def _peer(relay, username, pool, seed=None):
    return PeerCoordinator(relay=relay, party_id=0, username=username,
                           pool=pool, actuals_fn=_actuals, seed=seed)


def _run(coro):
    return asyncio.run(coro)


def _state(coord):
    """The local dungeon state that must match byte-for-byte across clients."""
    v = coord.view()
    return (v["depth"], v["power"], v["wounds"], v["threat"], v["percent"],
            tuple(v["window_colors"]), tuple(v["log"]), coord.session.state.to_dict())


def _start_two(relay, pool, seed=4242):
    """Creator (api-lead) + one follower, both joined and shopped into play."""
    lead = _peer(relay, "drpaj", pool, seed=seed)
    follower = _peer(relay, "alice", pool)            # follower adopts the seed from the blob
    _run(lead.join())
    _run(follower.join())
    _run(lead.leader_start())                          # lobby -> shop, seed + treasury
    for c in (lead, follower):
        _run(c.refresh())
        _run(c.submit_loadout([], c.shop_budget()))
    for c in (lead, follower):
        _run(c.refresh())
        _run(c.leader_try_reconcile_shop())            # no barrier -> both in play locally
    return lead, follower


def test_creator_sets_seed_and_follower_adopts_it():
    relay, pool = LocalRelay(), _pool()
    lead = _peer(relay, "drpaj", pool, seed=777)
    follower = _peer(relay, "alice", pool)
    _run(lead.join())
    _run(follower.join())
    assert lead.is_api_lead and lead.polls_api
    assert not follower.is_api_lead and not follower.polls_api
    assert lead.is_leader and follower.is_leader        # both resolve locally
    assert lead.seed == 777 and follower.seed == 777    # follower took it from the blob


def test_two_clients_compute_byte_identical_state_each_window():
    relay, pool = LocalRelay(), _pool()
    lead, follower = _start_two(relay, pool)
    preds = {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}
    for w in (1, 2, 3):
        # One-window-ahead: both submit window w's picks, the lead resolves (freezing + sharing
        # the bundle), then the follower replays the bundle from the blob.
        for c in (lead, follower):
            _run(c.submit_pick(w, preds))
        _run(lead.refresh())
        assert _run(lead.leader_try_resolve(w)) is True
        _run(follower.refresh())
        assert _run(follower.leader_try_resolve(w)) is True
        assert lead.resolved_through() == w and follower.resolved_through() == w
        assert _state(lead) == _state(follower)
    assert lead.view()["depth"] > 0


def test_follower_resolves_from_bundle_even_without_its_own_pick():
    # The follower never submits a pick for the window. The api-lead freezes inputs (defaulting
    # the follower's line) and shares the bundle; the follower replays it and still lands on the
    # SAME state -- no waiting on the missing pick, no divergence.
    relay, pool = LocalRelay(), _pool()
    lead, follower = _start_two(relay, pool)
    _run(lead.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    _run(lead.refresh())
    assert _run(lead.leader_try_resolve(1)) is True
    _run(follower.refresh())
    assert _run(follower.leader_try_resolve(1)) is True
    assert _state(lead) == _state(follower)


def test_follower_not_ready_until_bundle_arrives():
    # Before the api-lead shares the bundle, a follower's resolve is a no-op (returns False) --
    # it is gated on the bundle, never on a leader push it cannot see.
    relay, pool = LocalRelay(), _pool()
    lead, follower = _start_two(relay, pool)
    _run(follower.refresh())
    assert _run(follower.leader_try_resolve(1)) is False
    assert follower.resolved_through() == 0


def test_no_shop_reconcile_barrier():
    # A peer reconciles (enters play) the instant it shops, regardless of whether other members
    # are ready -- the old all-ready barrier is gone.
    relay, pool = LocalRelay(), _pool()
    lead = _peer(relay, "drpaj", pool, seed=1)
    follower = _peer(relay, "alice", pool)
    _run(lead.join())
    _run(follower.join())
    _run(lead.leader_start())
    _run(lead.refresh())
    _run(lead.submit_loadout([], lead.shop_budget()))   # follower has NOT shopped / readied
    assert _run(lead.leader_try_reconcile_shop()) is True
    assert lead.session is not None and lead.session.party_size == 2


def test_half_advance_resets_local_progress_and_clears_bundles():
    relay, pool = LocalRelay(), _pool()
    lead, follower = _start_two(relay, pool)
    preds = {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}
    for w in (1, 2, 3):
        for c in (lead, follower):
            _run(c.submit_pick(w, preds))
        _run(lead.refresh())
        _run(lead.leader_try_resolve(w))
        _run(follower.refresh())
        _run(follower.leader_try_resolve(w))
    _run(lead.leader_advance_half())
    _run(follower.leader_advance_half())
    assert lead.half() == 2 and follower.half() == 2
    assert lead.resolved_through() == 0 and follower.resolved_through() == 0
    assert lead.session.half == 2 and follower.session.half == 2
    _run(follower.refresh())
    assert follower.party.window_actuals == {}          # stale H1 bundles cleared for H2
    # H2 resolves and stays byte-identical across clients.
    for c in (lead, follower):
        _run(c.submit_pick(1, preds))
    _run(lead.refresh())
    _run(lead.leader_try_resolve(1))
    _run(follower.refresh())
    _run(follower.leader_try_resolve(1))
    assert _state(lead) == _state(follower)
