# src/game/live_resolver.py
"""Resolve a picked schedule game to its REAL API-Football fixture id at play time.

The offline schedule carries synthetic ids and full team names; the live relay
(live_fixtures.php, a filtered proxy of fixtures?live=all) reports whatever World Cup match
is in play right now as {id, home, away, ...}. This module matches the two by team name so
the live data pipeline can key on a real fixture id -- without ever prefetching or storing
one. ZERO pygame, fully unit-tested.

Matching is tolerant: names are lowercased, accent-stripped, and reduced to letters/digits,
then run through a small alias map for the handful of teams API-Football spells differently
from the schedule (Korea Republic vs South Korea, DR Congo vs Congo DR, etc.). A fixture
matches when its two teams equal the picked game's two teams, regardless of home/away order.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

# Normalized-form aliases: map an API/schedule spelling to one shared canonical token. Keys
# and values are already in normalized form (lowercase, accents stripped, letters/digits
# only). Both sides of a comparison are normalized AND aliased, so listing either spelling
# as a key pointing at a common value is enough.
_ALIASES = {
    "korearepublic": "southkorea",
    "republicofkorea": "southkorea",
    "drcongo": "congodr",
    "democraticrepublicofcongo": "congodr",
    "czechrepublic": "czechia",
    "bosniaandherzegovina": "bosniaherzegovina",
    "turkey": "turkiye",
    "caboverde": "capeverde",
    "cotedivoire": "ivorycoast",
    "usa": "unitedstates",
    "unitedstatesofamerica": "unitedstates",
    "iranislamicrepublicof": "iran",
    "iriran": "iran",
}


def _norm(name: Any) -> str:
    """Lowercase, strip accents, keep only letters/digits, then apply the alias map.
    'Curacao'/'Curacao' -> 'curacao'; 'Korea Republic' -> 'southkorea'."""
    if not isinstance(name, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    token = "".join(c for c in ascii_only.lower() if c.isalnum())
    return _ALIASES.get(token, token)


def resolve_fixture_id(home: str, away: str,
                       live_response: Optional[list[dict]]) -> Optional[int]:
    """Return the real fixture id whose two teams match (home, away) in any order, or None.

    `live_response` is the `response` list from live_fixtures.php: each entry has `id`,
    `home`, `away`. A blank picked team never matches (avoids matching an empty API field)."""
    want = {_norm(home), _norm(away)}
    if "" in want or len(want) != 2:
        return None
    for fx in live_response or []:
        if not isinstance(fx, dict):
            continue
        fid = fx.get("id")
        if fid is None:
            continue
        got = {_norm(fx.get("home")), _norm(fx.get("away"))}
        if got == want:
            try:
                return int(fid)
            except (TypeError, ValueError):
                return None
    return None
