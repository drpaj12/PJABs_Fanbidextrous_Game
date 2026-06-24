from src.game.party import (Member, Party, parse_preds, preds_from_lines,
                            fighter_lines_from_picks, used_consumables_from_picks,
                            split_gold, DEFAULT_LINES)


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


def test_seed_and_window_actuals_default_and_round_trip():
    # Peer-computed co-op stores the creator's session seed and the lead's per-window input
    # bundles in the blob. Both must default cleanly and survive a to_dict/from_dict round-trip.
    p = Party.create(party_id=2, leader="drpaj")
    assert p.seed is None and p.window_actuals == {}
    p.seed = 4242
    p.window_actuals = {"1": {"actuals": {"goal": 1}, "lines": [{"goal": 1}], "use": [["7"]]}}
    again = Party.from_dict(p.to_dict())
    assert again.seed == 4242
    assert again.window_actuals == p.window_actuals
    assert again.to_dict() == p.to_dict()


def test_from_dict_tolerates_malformed_window_actuals_and_seed():
    # Like window_picks, a stale shared room file can hold a malformed window_actuals payload;
    # from_dict must drop non-dict garbage and tolerate a missing/blank seed without crashing.
    base = Party.create(party_id=0, leader="drpaj").to_dict()
    assert Party.from_dict({**base, "window_actuals": ["x"]}).window_actuals == {}
    assert Party.from_dict({**base, "window_actuals": "nope"}).window_actuals == {}
    mixed = {"1": {"actuals": {"goal": 1}}, "2": ["bad"]}
    assert Party.from_dict({**base, "window_actuals": mixed}).window_actuals == {
        "1": {"actuals": {"goal": 1}}}
    assert Party.from_dict({**base, "seed": None}).seed is None
    assert Party.from_dict({**base}).seed is None


def test_from_dict_tolerates_malformed_window_picks():
    # Party 0 is a long-lived shared test room; a stale session file can hold a window_picks
    # of the wrong shape (e.g. a list from an older format). from_dict must not crash and must
    # drop the garbage, keeping only well-formed dict entries.
    base = Party.create(party_id=0, leader="drpaj").to_dict()
    assert Party.from_dict({**base, "window_picks": ["abc", "def"]}).window_picks == {}
    assert Party.from_dict({**base, "window_picks": "nonsense"}).window_picks == {}
    mixed = {"0": {"w": 1, "preds": ["goal:1"]}, "1": ["not", "a", "dict"]}
    assert Party.from_dict({**base, "window_picks": mixed}).window_picks == {
        "0": {"w": 1, "preds": ["goal:1"]}}


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


def test_parse_and_format_preds_round_trip():
    lines = {"goal": 1, "shot": 3, "corner": 2, "card": 0, "foul": 5}
    preds = preds_from_lines(lines)
    assert "goal:1" in preds and "shot:3" in preds and len(preds) == 5
    assert parse_preds(preds) == lines


def test_parse_preds_drops_unknown_and_malformed():
    assert parse_preds(["goal:2", "bogus:9", "garbage", "shot:x"]) == {"goal": 2}


def test_fighter_lines_orders_by_slot_and_default_fills():
    p = Party.create(party_id=0, leader="drpaj")     # slot 0
    p.join_or_restore("alice", max_size=3)           # slot 1
    p.window_picks = {"1": {"w": 2, "preds": ["goal:3", "shot:9"]}}
    lines = fighter_lines_from_picks(p, window=2)
    assert len(lines) == 2
    assert lines[0] == DEFAULT_LINES                 # slot 0 did not submit
    assert lines[1]["goal"] == 3 and lines[1]["shot"] == 9
    assert lines[1]["corner"] == DEFAULT_LINES["corner"]


def test_fighter_lines_ignores_other_windows():
    p = Party.create(party_id=0, leader="drpaj")
    p.window_picks = {"0": {"w": 1, "preds": ["goal:5"]}}
    assert fighter_lines_from_picks(p, window=2) == [DEFAULT_LINES]


def test_used_consumables_orders_by_slot_and_empties_non_submitters():
    p = Party.create(party_id=0, leader="drpaj")     # slot 0
    p.join_or_restore("alice", max_size=3)           # slot 1
    p.window_picks = {"1": {"w": 2, "preds": ["goal:3"], "use": ["sccr-3"]}}
    used = used_consumables_from_picks(p, window=2)
    assert used == [[], ["sccr-3"]]                  # slot 0 submitted nothing


def test_used_consumables_ignores_other_windows_and_missing_key():
    p = Party.create(party_id=0, leader="drpaj")
    p.window_picks = {"0": {"w": 1, "preds": ["goal:5"], "use": ["sccr-3"]}}
    assert used_consumables_from_picks(p, window=2) == [[]]   # window mismatch
    p.window_picks = {"0": {"w": 2, "preds": ["goal:5"]}}     # no "use" key
    assert used_consumables_from_picks(p, window=2) == [[]]


def test_all_picks_in():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("alice", max_size=3)
    p.window_picks = {"0": {"w": 1, "preds": ["goal:1"]}}
    assert p.all_picks_in(window=1) is False
    p.window_picks["1"] = {"w": 1, "preds": ["goal:2"]}
    assert p.all_picks_in(window=1) is True


def test_split_gold_is_equal_with_remainder_to_lowest_slots():
    assert split_gold(90, 3) == [30, 30, 30]
    assert split_gold(100, 3) == [34, 33, 33]   # remainder 1 -> slot 0
    assert split_gold(7, 1) == [7]
    assert split_gold(5, 0) == []
