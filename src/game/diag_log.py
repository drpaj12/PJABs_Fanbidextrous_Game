# src/game/diag_log.py
"""Developer diagnostic trail for the realtime SIM harness. No pygame -- a pure line buffer
the flow writes to and a screen drains into its existing scrollable LogList.

Every line is tagged with an ACTOR so a co-op run reads as ONE combined timeline: this
client's own actions plus the OTHER client's actions observed from the shared relay blob,
each stamped with the (sim) minute and the time-since-kickoff it happened.

ASCII only (project rule): line shape is
    [<actor>] t=+MM:SS min=NN' KIND detail
where t is signed seconds-from-kickoff (negative pre-kickoff) and min is the absolute
match minute. The lead client's actor tag is its username (e.g. "drpaj"); peer lines carry
the other player's name.
"""
from typing import Optional


def _stamp(seconds_from_kickoff: int) -> str:
    """Signed +MM:SS / -MM:SS time-since-kickoff stamp."""
    sign = "-" if seconds_from_kickoff < 0 else "+"
    s = abs(int(seconds_from_kickoff))
    return f"{sign}{s // 60:02d}:{s % 60:02d}"


class DiagLog:
    def __init__(self, enabled: bool, actor: str) -> None:
        self.enabled = enabled
        self.actor = actor
        self._lines: list[str] = []
        self._drained = 0

    def _emit(self, actor: str, minute: int, kind: str, detail: str,
              seconds_from_kickoff: Optional[int]) -> None:
        if not self.enabled:
            return
        t = _stamp(seconds_from_kickoff if seconds_from_kickoff is not None else minute * 60)
        line = f"[{actor}] t={t} min={minute}' {kind}"
        if detail:
            line += f" {detail}"
        self._lines.append(line)

    def add(self, minute: int, kind: str, detail: str = "",
            seconds_from_kickoff: Optional[int] = None) -> None:
        """Record one local action under this client's actor tag."""
        self._emit(self.actor, minute, kind, detail, seconds_from_kickoff)

    def add_peer(self, peer: str, minute: int, kind: str, detail: str = "",
                 seconds_from_kickoff: Optional[int] = None) -> None:
        """Record one OBSERVED peer action (from the shared blob) under the peer's tag."""
        self._emit(peer, minute, kind, detail, seconds_from_kickoff)

    def drain(self) -> list[str]:
        """Return the lines added since the last drain (and mark them shown). The play screen
        appends these to its scrollable LogList each frame."""
        new = self._lines[self._drained:]
        self._drained = len(self._lines)
        return new

    def all_lines(self) -> list[str]:
        """Full history (for tests / a post-run dump)."""
        return list(self._lines)
