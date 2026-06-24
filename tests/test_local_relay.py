import asyncio

from src.game.party import Party
from src.sync.local_relay import LocalRelay


def test_first_join_creates_party_and_makes_caller_leader():
    relay = LocalRelay()
    resp = asyncio.run(relay.party_join(0, "drpaj"))
    assert resp == {"success": True, "slot": 0, "is_leader": True}
    state = asyncio.run(relay.party_state(0))
    assert Party.from_dict(state["party"]).leader == "drpaj"


def test_solo_party_of_one_round_trips_pick_loadout_and_push():
    relay = LocalRelay()
    asyncio.run(relay.party_join(7, "drpaj"))
    asyncio.run(relay.party_loadout(7, "drpaj", ["sccr-1"], 250))
    asyncio.run(relay.party_pick(7, "drpaj", 1, ["goal:2"], use=["sccr-1"]))
    p = Party.from_dict(asyncio.run(relay.party_state(7))["party"])
    assert p.members[0].items == ["sccr-1"] and p.members[0].treasury == 250
    assert p.members[0].ready is True
    assert p.window_picks["0"] == {"w": 1, "preds": ["goal:2"], "use": ["sccr-1"]}

    asyncio.run(relay.party_push(7, "drpaj", {"phase": "play", "clear_picks": True}))
    p2 = Party.from_dict(asyncio.run(relay.party_state(7))["party"])
    assert p2.phase == "play" and p2.window_picks == {}


def test_second_join_takes_next_slot_and_is_not_leader():
    relay = LocalRelay()
    asyncio.run(relay.party_join(0, "drpaj"))
    resp = asyncio.run(relay.party_join(0, "cam"))
    assert resp["slot"] == 1 and resp["is_leader"] is False
