# tests/test_live_resolver.py
"""Resolve a picked schedule game to its real API-Football id (golden rule: no pygame)."""
from src.game.live_resolver import resolve_fixture_id


def fx(fid, home, away):
    return {"id": fid, "home": home, "away": away, "status": "1H", "elapsed": 12}


SPAIN_SAUDI = [fx(1489397, "Spain", "Saudi Arabia"), fx(1539006, "Belgium", "Iran")]


def test_exact_match_returns_id():
    assert resolve_fixture_id("Spain", "Saudi Arabia", SPAIN_SAUDI) == 1489397


def test_home_away_order_does_not_matter():
    # picked game lists the teams swapped relative to the live feed
    assert resolve_fixture_id("Saudi Arabia", "Spain", SPAIN_SAUDI) == 1489397


def test_second_game_in_list_matches():
    assert resolve_fixture_id("Belgium", "Iran", SPAIN_SAUDI) == 1539006


def test_no_match_returns_none():
    assert resolve_fixture_id("Brazil", "Argentina", SPAIN_SAUDI) is None


def test_accents_are_stripped():
    feed = [fx(42, "Curacao", "Cote d'Ivoire")]
    assert resolve_fixture_id("Curacao", "Cote d'Ivoire", feed) == 42


def test_alias_korea_republic_matches_south_korea():
    feed = [fx(7, "Korea Republic", "Ghana")]
    assert resolve_fixture_id("South Korea", "Ghana", feed) == 7


def test_alias_dr_congo():
    feed = [fx(8, "Congo DR", "Senegal")]
    assert resolve_fixture_id("DR Congo", "Senegal", feed) == 8


def test_alias_iran_long_form():
    feed = [fx(9, "IR Iran", "Qatar")]
    assert resolve_fixture_id("Iran", "Qatar", feed) == 9


def test_alias_turkey_turkiye():
    feed = [fx(10, "Turkiye", "Portugal")]
    assert resolve_fixture_id("Turkey", "Portugal", feed) == 10


def test_alias_usa():
    feed = [fx(11, "USA", "Mexico")]
    assert resolve_fixture_id("United States", "Mexico", feed) == 11


def test_blank_picked_team_never_matches():
    feed = [fx(1, "", "Spain")]
    assert resolve_fixture_id("", "Spain", feed) is None


def test_empty_live_response_returns_none():
    assert resolve_fixture_id("Spain", "Saudi Arabia", []) is None
    assert resolve_fixture_id("Spain", "Saudi Arabia", None) is None


def test_string_id_is_coerced_to_int():
    feed = [{"id": "1489397", "home": "Spain", "away": "Saudi Arabia"}]
    assert resolve_fixture_id("Spain", "Saudi Arabia", feed) == 1489397


def test_entry_missing_id_is_skipped():
    feed = [{"home": "Spain", "away": "Saudi Arabia"}, fx(99, "Spain", "Saudi Arabia")]
    assert resolve_fixture_id("Spain", "Saudi Arabia", feed) == 99


def test_non_dict_entries_are_ignored():
    feed = ["garbage", None, 42, fx(5, "Spain", "Saudi Arabia")]
    assert resolve_fixture_id("Spain", "Saudi Arabia", feed) == 5


def test_same_team_twice_is_not_a_valid_pick():
    assert resolve_fixture_id("Spain", "Spain", SPAIN_SAUDI) is None
