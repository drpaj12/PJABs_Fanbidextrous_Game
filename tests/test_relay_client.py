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
