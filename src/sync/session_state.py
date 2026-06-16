"""Local session bookkeeping: room/token identity, window math, known score events.

slot (0/1) is derived from the relay's my_player (1/2) and is used when stamping this
client's own score-event codes. seed comes once from the room and feeds the shared RNG.
"""
from src.game.scoring import aggregate
from src.utils.constants import CONFIG


class SessionState:
    def __init__(self, room: int, token: str, seed: int, slot: int) -> None:
        self.room = room
        self.token = token
        self.seed = seed
        self.slot = slot
        self.score_events: list[str] = []
        self._window_minutes = CONFIG["game"]["window_seconds"] // 60

    def window_for_minute(self, minute: int) -> int:
        return minute // self._window_minutes + 1

    def add_score_event(self, code: str) -> None:
        if code not in self.score_events:
            self.score_events.append(code)

    def shared_score(self) -> tuple[int, int]:
        return aggregate(self.score_events)
