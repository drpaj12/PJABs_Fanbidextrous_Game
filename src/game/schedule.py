# src/game/schedule.py
"""Pure schedule logic for the live-game viewer: parse a curated game list and derive each
game's status and 'how soon' label from the wall clock. ZERO pygame -- fully unit-tested.

Time math uses kickoff_utc (parsed to epoch) only. kickoff_local is a pre-baked US Eastern
display string the curator bakes EST/EDT correctness into, so no timezone library is needed
(the pygbag/WASM runtime ships no tzdata). Every time-dependent function takes `now` (epoch
seconds) as a parameter, so behavior is deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

_REQUIRED_KEYS = ("id", "competition", "home", "away", "round",
                  "kickoff_utc", "kickoff_local")
_DAY = 24 * 3600


def _derive_abbr(name: str) -> str:
    """Fallback 3-letter code from a team name: the uppercased first three letters of its
    longest word (ties resolve to the first). 'Netherlands'->'NET', 'Ivory Coast'->'IVO'."""
    words = [w for w in name.split() if w]
    if not words:
        return name[:3].upper()
    longest = max(words, key=len)
    return longest[:3].upper()


def _parse_epoch(iso: Any) -> Optional[float]:
    """Parse an ISO 8601 UTC timestamp ('...Z' or '...+00:00') to epoch seconds, or None.

    Uses .timestamp() on a tz-aware datetime, so the result is independent of the host
    machine's local timezone (important for WASM and deterministic tests)."""
    if not isinstance(iso, str) or not iso:
        return None
    text = iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@dataclass(frozen=True)
class ScheduledGame:
    id: int
    competition: str
    home: str
    away: str
    round: str
    kickoff_utc: str
    kickoff_local: str
    home_abbr: str = ""
    away_abbr: str = ""

    def title(self) -> str:
        """'Home v Away' when both teams are known, else the round descriptor."""
        if self.home and self.away:
            return f"{self.home} v {self.away}"
        return self.round

    def short_title(self) -> str:
        """Compact 'NED v SWE' so the title fits the card. Uses the curated abbr fields,
        falls back to a derived 3-letter code per team, then to the round descriptor."""
        if self.home and self.away:
            home = self.home_abbr or _derive_abbr(self.home)
            away = self.away_abbr or _derive_abbr(self.away)
            return f"{home} v {away}"
        return self.round

    def kickoff_epoch(self) -> Optional[float]:
        """kickoff_utc parsed to epoch seconds, or None if unparseable."""
        return _parse_epoch(self.kickoff_utc)


def load_schedule(raw: dict) -> list[ScheduledGame]:
    """Parse raw['games'] into ScheduledGame objects, skipping any malformed record
    (not a dict, missing a required key, or with an unparseable kickoff_utc)."""
    games: list[ScheduledGame] = []
    for rec in (raw or {}).get("games", []):
        if not isinstance(rec, dict):
            continue
        if any(k not in rec for k in _REQUIRED_KEYS):
            continue
        if _parse_epoch(rec["kickoff_utc"]) is None:
            continue
        try:
            game = ScheduledGame(
                id=int(rec["id"]),
                competition=str(rec["competition"]),
                home=str(rec["home"]),
                away=str(rec["away"]),
                round=str(rec["round"]),
                kickoff_utc=str(rec["kickoff_utc"]),
                kickoff_local=str(rec["kickoff_local"]),
                home_abbr=str(rec.get("home_abbr", "")),
                away_abbr=str(rec.get("away_abbr", "")),
            )
        except (TypeError, ValueError):
            continue
        games.append(game)
    return games


def game_status(game: ScheduledGame, now: float, live_window_minutes: int) -> str:
    """'upcoming' before kickoff, 'live' during the generous live window, 'final' after.
    A game with no parseable kickoff is treated as 'final' (defensive)."""
    kickoff = game.kickoff_epoch()
    if kickoff is None:
        return "final"
    if now < kickoff:
        return "upcoming"
    if now < kickoff + live_window_minutes * 60:
        return "live"
    return "final"


def status_label(game: ScheduledGame, now: float, soon_minutes: int,
                 live_window_minutes: int) -> str:
    """Chip text: 'in 2h' / 'in 1d' / 'in 15m' / 'soon' / 'LIVE NOW' / 'Final'.
    For upcoming games the largest whole unit is used (days >= 24h, else hours >= 60m,
    else minutes); within soon_minutes of kickoff it reads 'soon'."""
    status = game_status(game, now, live_window_minutes)
    if status == "live":
        return "LIVE NOW"
    if status == "final":
        return "Final"
    kickoff = game.kickoff_epoch()
    secs = (kickoff if kickoff is not None else now) - now
    if secs <= soon_minutes * 60:
        return "soon"
    if secs >= _DAY:
        return f"in {int(secs // _DAY)}d"
    if secs >= 3600:
        return f"in {int(secs // 3600)}h"
    return f"in {int(secs // 60)}m"


def is_playable(game: ScheduledGame, now: float, live_window_minutes: int) -> bool:
    """Upcoming AND live games are tappable; finished games are not."""
    return game_status(game, now, live_window_minutes) != "final"


def visible_games(games: list[ScheduledGame], now: float,
                  cfg: dict) -> list[ScheduledGame]:
    """Rolling window: keep games from drop_after_hours after kickoff back through
    lookahead_hours before, sorted soonest-first. Records with no parseable kickoff drop."""
    lookahead = int(cfg["lookahead_hours"]) * 3600
    drop_after = int(cfg["drop_after_hours"]) * 3600
    kept: list[tuple[float, ScheduledGame]] = []
    for g in games:
        kickoff = g.kickoff_epoch()
        if kickoff is None:
            continue
        delta = kickoff - now
        if -drop_after <= delta <= lookahead:
            kept.append((kickoff, g))
    kept.sort(key=lambda pair: pair[0])
    return [g for _, g in kept]
