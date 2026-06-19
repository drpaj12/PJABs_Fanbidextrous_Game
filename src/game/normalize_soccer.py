# src/game/normalize_soccer.py
"""Pure normalization of API-Football v3 JSON into engine models. No network here."""
from typing import Iterable
from src.game.athlete import DraftedAthlete
from src.utils.constants import CONFIG

_POS_MAP = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}

# API-Football fixture status short codes -> engine status vocabulary. The single place
# the API's status names meet the engine's. Unknown codes default to "live".
_STATUS_MAP = {
    "TBD": "scheduled", "NS": "scheduled", "PST": "scheduled", "CANC": "finished",
    "1H": "live", "2H": "live", "ET": "live", "BT": "live", "P": "live",
    "LIVE": "live", "INT": "live", "SUSP": "live",
    "HT": CONFIG["feed"]["halftime_status"],
    "FT": "finished", "AET": "finished", "PEN": "finished", "ABD": "finished",
    "AWD": "finished", "WO": "finished",
}


def map_status(short: str) -> str:
    """Map an API-Football fixture status short code to the engine's status string."""
    return _STATUS_MAP.get((short or "").upper(), "live")
_STAT_FIELD = {
    "Corner Kicks": "corner_kicks",
    "Shots on Goal": "shots_on_goal",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total Shots": "total_shots",
    "Fouls": "fouls",
    "Yellow Cards": "cards",
    "Red Cards": "cards",
}


def _athlete(player: dict, team_name: str) -> DraftedAthlete:
    p = player["player"]
    broad = _POS_MAP.get((p.get("pos") or "M").upper()[:1], "Midfielder")
    return DraftedAthlete.create(
        athlete_id=f"sccr-{p['id']}", name=p.get("name", "Unknown"),
        broad_position=broad, team=team_name, jersey=p.get("number") or 0)


def parse_lineups(data: dict,
                  groups: Iterable[str] = ("startXI", "substitutes")) -> list[DraftedAthlete]:
    """Flatten API-Football lineups into athletes. `groups` selects which player lists to
    include; the live feed passes ("startXI",) to draft only the 22 starters."""
    out: list[DraftedAthlete] = []
    for team_block in data.get("response", []):
        team_name = team_block.get("team", {}).get("name", "")
        for group in groups:
            for player in team_block.get(group, []) or []:
                out.append(_athlete(player, team_name))
    return out


def parse_statistics(data: dict) -> dict[str, int]:
    stats: dict[str, int] = {}
    for team_block in data.get("response", []):
        for entry in team_block.get("statistics", []) or []:
            field_name = _STAT_FIELD.get(entry.get("type", ""))
            if field_name is None:
                continue
            value = entry.get("value")
            stats[field_name] = stats.get(field_name, 0) + int(value or 0)
    return stats


def actuals_from_raw(raw: dict[str, int], menu: dict) -> dict[str, int]:
    """Translate API-field-keyed stats into engine stat codes via stats_menu api_field.

    Each menu stat maps its `api_field` value in `raw` to the stat `code` the engine
    grades against. Stats with no matching field in `raw` resolve to 0. This is the single
    bridge between the feed's key space and the engine's; both the live path and the demo
    use it. (The `goal` stat has no source in the statistics endpoint -- goals come from
    fixture/events data -- so it resolves to 0 here until the live events path is wired.)
    """
    return {s["code"]: int(raw.get(s["api_field"], 0)) for s in menu.get("stats", [])}
