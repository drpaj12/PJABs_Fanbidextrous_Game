import sys

from src.sync.relay_client import default_transport, UrllibTransport
from src.sync.wasm_transport import FetchTransport


def test_default_transport_desktop_is_urllib(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(default_transport(), UrllibTransport)


def test_default_transport_web_is_fetch(monkeypatch):
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert isinstance(default_transport(), FetchTransport)


def test_fetch_transport_satisfies_protocol():
    # The transport the relay/feed clients expect: async get(url) and post(url, body).
    t = FetchTransport()
    assert callable(t.get) and callable(t.post)
