# src/game/feed.py
"""EventFeed protocol: the only feed interface the engine depends on."""
from typing import Protocol
from src.game.sport_event import SportEvent, WindowSnapshot


class EventFeed(Protocol):
    def snapshot_at(self, minute: int) -> WindowSnapshot: ...
    def events_between(self, start_minute: int, end_minute: int) -> list[SportEvent]: ...
    def match_status(self) -> str: ...
