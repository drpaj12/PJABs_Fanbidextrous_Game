import asyncio
import json
from src.sync.relay_client import RelayClient


class _FakeTransport:
    def __init__(self):
        self.gets: list[str] = []
        self.posts: list[tuple[str, str]] = []

    async def get(self, url: str) -> str:
        self.gets.append(url)
        return json.dumps({"success": True, "phase": "playing", "current_turn": 2,
                           "seed": 424242, "my_player": 1})

    async def post(self, url: str, body: str) -> str:
        self.posts.append((url, body))
        return json.dumps({"success": True})


def test_join_uses_action_and_room():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.join(room=2))
    assert "action=join" in t.posts[0][0] and "room=2" in t.posts[0][0]


def test_get_state_passes_token_and_parses():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    state = asyncio.run(client.get_state(room=0, token="abc"))
    assert "action=state" in t.gets[0] and "token=abc" in t.gets[0]
    assert state["seed"] == 424242


def test_submit_window_sends_type_and_predictions():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.submit_window(room=0, token="abc", window=1,
                                     predictions=["corner:3", "shot:2"],
                                     active_id="sccr-1", use_power=True))
    body = t.posts[0][1]
    assert '"type": "window_submit"' in body
    assert "corner:3" in body and "sccr-1" in body


def test_submit_draft_and_score_event_have_distinct_types():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.submit_draft(room=0, token="abc", athlete_ids=["sccr-1"]))
    asyncio.run(client.submit_score_event(room=0, token="abc", code="0:1:for:1"))
    assert '"type": "draft_submit"' in t.posts[0][1]
    assert '"type": "score_event"' in t.posts[1][1]


def test_party_join_uses_action_party_and_username():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_join(party=2, username="drpaj"))
    url, body = t.posts[0]
    assert "action=party_join" in url and "party=2" in url
    assert '"type": "party_join"' in body and "drpaj" in body


def test_party_state_is_a_get():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_state(party=1))
    assert "action=party_state" in t.gets[0] and "party=1" in t.gets[0]


def test_party_pick_carries_window_and_preds():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_pick(party=0, username="a", window=2, preds=["goal:1", "shot:3"]))
    url, body = t.posts[0]
    assert "action=party_pick" in url
    assert '"window": 2' in body and "goal:1" in body


def test_party_loadout_carries_items_and_treasury():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_loadout(party=0, username="a", item_ids=["1"], treasury=120))
    body = t.posts[0][1]
    assert '"type": "party_loadout"' in body and '"treasury": 120' in body and '"1"' in body


def test_party_push_carries_arbitrary_state():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_push(party=0, username="drpaj",
                                  state={"phase": "play", "clear_picks": True}))
    body = t.posts[0][1]
    assert '"type": "party_push"' in body and '"phase": "play"' in body and '"clear_picks": true' in body
