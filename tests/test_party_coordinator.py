import asyncio

from src.game.athlete import DraftedAthlete
from src.game.party import Party
from src.sync.party_coordinator import PartyCoordinator
# LocalRelay is the production in-process relay (the SOLO crawl uses it). It is byte-for-byte
# the old in-memory FakeRelay these tests were written against, so the coordinator suite now
# exercises the real solo transport rather than a duplicate test double.
from src.sync.local_relay import LocalRelay as FakeRelay


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


def _consumable_id(pool):
    from src.game.items import build_catalog
    return next(it.item_id for it in build_catalog(pool, 1, 1.0) if it.category == "consumable")


def _setup_solo_with_consumable(relay, pool, cons_id):
    """Leader-only party that bought one consumable, reconciled into play."""
    lead = _coord(relay, "drpaj", pool)
    _join_all(lead)
    asyncio.run(lead.leader_start())
    asyncio.run(lead.refresh())
    asyncio.run(lead.submit_loadout([cons_id], lead.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(lead.refresh())
    return lead


def test_used_potion_is_consumed_from_inventory_on_resolve():
    relay, pool = FakeRelay(), _pool()
    cons_id = _consumable_id(pool)
    lead = _setup_solo_with_consumable(relay, pool, cons_id)
    asyncio.run(lead.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4},
                                 use=[cons_id]))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    asyncio.run(lead.refresh())
    assert cons_id not in lead.me().items                  # deployed -> gone
    assert cons_id not in [it.item_id for it in lead.session.loadouts[0].items]


def test_unused_potion_persists_in_inventory_after_resolve():
    relay, pool = FakeRelay(), _pool()
    cons_id = _consumable_id(pool)
    lead = _setup_solo_with_consumable(relay, pool, cons_id)
    asyncio.run(lead.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    asyncio.run(lead.refresh())
    assert cons_id in lead.me().items                      # held, not used -> kept
    assert cons_id in [it.item_id for it in lead.session.loadouts[0].items]


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


def test_leader_catch_up_resolves_every_window_through_target_with_defaults():
    """Live catch-up: the leader fast-forwards past windows the match already played by
    resolving each with defaults (no member submitted picks for past windows). One call
    resolves windows 1..target in order and lands resolved_through at the target."""
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(lead.refresh())
    # No picks submitted for any window -- pure catch-up with defaults.
    resolved = asyncio.run(lead.leader_catch_up(2))
    assert resolved == 2 and lead.resolved_through() == 2
    asyncio.run(a.refresh())
    assert a.resolved_through() == 2 and a.view()["depth"] > 0


def test_leader_catch_up_is_idempotent_and_only_advances_forward():
    """Calling catch-up to a window already behind resolved_through does nothing; the count
    never regresses. A second call to the same target is a no-op."""
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(lead.refresh())
    assert asyncio.run(lead.leader_catch_up(2)) == 2
    # Target behind the front -- no regression, stays at 2.
    assert asyncio.run(lead.leader_catch_up(1)) == 2
    # Same target again -- idempotent no-op.
    assert asyncio.run(lead.leader_catch_up(2)) == 2
    assert lead.resolved_through() == 2


def test_follower_catch_up_is_a_noop():
    """Only the leader resolves; a follower's catch-up call returns its current
    resolved_through without resolving anything."""
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(a.refresh())
    assert asyncio.run(a.leader_catch_up(3)) == 0
    assert a.resolved_through() == 0


def test_follower_percent_matches_leader_after_h2_window():
    """Drive a 2-member party through all H1 windows, advance to H2, reconcile H2 shop,
    resolve one H2 window, then assert that a follower (no local session) sees the same
    view()["percent"] as the leader.  Before the cleared_prev fix this would be wrong
    because followers had cleared_prev=0 and so under-reported progress by a full half."""
    # windows_per_half = 3 (game.windows_per_half in game_config.json)
    WINDOWS_PER_HALF = 3
    PICKS = {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}

    relay, pool = FakeRelay(), _pool()
    lead = _coord(relay, "drpaj", pool)
    follower = _coord(relay, "alice", pool)
    _join_all(lead, follower)

    # --- H1 shop ---
    asyncio.run(lead.leader_start())
    for c in (lead, follower):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, follower):
        asyncio.run(c.refresh())
    assert lead.phase() == "play"

    # --- H1 play: resolve all windows ---
    for w in range(1, WINDOWS_PER_HALF + 1):
        for c in (lead, follower):
            asyncio.run(c.submit_pick(w, PICKS))
        asyncio.run(lead.refresh())
        ok = asyncio.run(lead.leader_try_resolve(w))
        assert ok, f"H1 window {w} should resolve"
    asyncio.run(follower.refresh())
    assert lead.resolved_through() == WINDOWS_PER_HALF

    # --- advance to H2 ---
    asyncio.run(lead.leader_advance_half())
    for c in (lead, follower):
        asyncio.run(c.refresh())
    assert lead.phase() == "shop" and lead.half() == 2

    # --- H2 shop ---
    for c in (lead, follower):
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, follower):
        asyncio.run(c.refresh())
    assert lead.phase() == "play"

    # --- resolve one H2 window ---
    for c in (lead, follower):
        asyncio.run(c.submit_pick(1, PICKS))
    asyncio.run(lead.refresh())
    ok = asyncio.run(lead.leader_try_resolve(1))
    assert ok, "H2 window 1 should resolve"

    # --- build a fresh follower coord (no local session) and refresh from relay ---
    fresh_follower = _coord(relay, "alice", pool)
    asyncio.run(fresh_follower.join())   # restores slot via join_or_restore

    # Both the leader and the fresh follower must report identical percent.
    # The leader uses self.session.cleared_prev_halves; the follower reads it from
    # the dungeon blob (cleared_prev key written by _push_after_resolve).
    leader_pct = lead.view()["percent"]
    follower_pct = fresh_follower.view()["percent"]
    assert leader_pct > 0, "leader percent should be non-zero after H1 + 1 H2 window"
    assert follower_pct == leader_pct, (
        f"follower percent {follower_pct} != leader percent {leader_pct}; "
        "cleared_prev is not propagating through the blob"
    )
