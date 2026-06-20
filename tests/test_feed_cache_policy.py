from src.game import feed_cache_policy as p


def test_cache_key_is_normalised_by_username_and_fixture():
    assert p.cache_key("  DrPAJ ", 1539007) == p.cache_key("drpaj", 1539007)
    assert p.cache_key("a", 1) != p.cache_key("a", 2)
    assert p.cache_key("a", 1) != p.cache_key("b", 1)


def test_make_blob_then_round_trip():
    blob = p.make_blob({"fixture": {"x": 1}}, now=100.0)
    assert blob["cached_at"] == 100.0
    assert blob["snapshot"] == {"fixture": {"x": 1}}
    text = p.serialize(blob)
    assert p.deserialize(text) == blob


def test_deserialize_bad_text_is_none():
    assert p.deserialize("not json") is None
    assert p.deserialize(None) is None


def test_should_poll_on_start():
    blob = p.make_blob({}, now=100.0)
    # within poll window -> warm start, no poll
    assert p.should_poll_on_start(blob, now=200.0, poll_seconds=300) is False
    # older than poll window -> poll for fresh data
    assert p.should_poll_on_start(blob, now=500.0, poll_seconds=300) is True
    # no cache at all -> must poll
    assert p.should_poll_on_start(None, now=10.0, poll_seconds=300) is True
