from src.game.party import Member, Party


def test_create_puts_leader_at_slot_zero_with_default_fields():
    p = Party.create(party_id=2, leader="Drpaj")
    assert p.leader == "drpaj"            # normalized
    assert p.phase == "lobby" and p.half == 1
    assert p.fixture_id == 0 and p.match["status"] == "NS"
    assert len(p.members) == 1
    m = p.members[0]
    assert m.username == "drpaj" and m.slot == 0 and m.treasury == 0 and m.ready is False


def test_round_trips_through_dict():
    p = Party.create(party_id=2, leader="drpaj")
    p.phase = "play"
    p.fixture_id = 12345
    p.match = {"home": "NED", "away": "SWE", "home_goals": 1,
               "away_goals": 0, "minute": 22, "status": "1H"}
    p.pool = [{"athlete_id": 1, "name": "P1", "broad_position": "Attacker",
               "team": "NED", "jersey": 9}]
    p.members[0].items = ["1"]
    p.members[0].treasury = 120
    p.members[0].ready = True
    p.log = ["W1 advance +6"]
    p.window_colors = ["green"]
    p.window_picks = {"0": {"w": 1, "preds": ["goal:1", "shot:3"]}}
    p.dungeon = {"half": 1, "party_size": 1, "depth": 6, "power": 1,
                 "wounds": 0, "threat": 0, "gates_passed": 0, "finished": False}
    again = Party.from_dict(p.to_dict())
    assert again.to_dict() == p.to_dict()
    assert again.members[0].treasury == 120 and again.members[0].ready is True
    assert again.match["home"] == "NED" and again.pool[0]["jersey"] == 9


def test_member_lookup_is_case_insensitive():
    p = Party.create(party_id=0, leader="drpaj")
    assert p.member("DRPAJ") is p.members[0]
    assert p.member("nobody") is None


def test_new_member_takes_next_free_slot():
    p = Party.create(party_id=0, leader="drpaj")
    assert p.join_or_restore("alice", max_size=3) == (1, True)
    assert p.member("alice").slot == 1
    assert p.join_or_restore("bob", max_size=3) == (2, True)


def test_rejoin_by_username_restores_seat():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("alice", max_size=3)            # slot 1
    assert p.join_or_restore("Alice", max_size=3) == (1, False)   # case-insensitive
    assert len(p.members) == 2


def test_full_party_rejects_new_member_but_admits_existing():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("a", max_size=3)
    p.join_or_restore("b", max_size=3)
    assert p.join_or_restore("c", max_size=3) == (None, False)
    assert len(p.members) == 3
    assert p.join_or_restore("drpaj", max_size=3) == (0, False)
