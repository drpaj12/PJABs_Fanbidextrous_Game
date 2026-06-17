# src/game/normalize_soccer.py
"""Pure normalization of API-Football v3 JSON into engine models. No network here."""
from src.game.athlete import DraftedAthlete

_POS_MAP = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}
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


def parse_lineups(data: dict) -> list[DraftedAthlete]:
    out: list[DraftedAthlete] = []
    for team_block in data.get("response", []):
        team_name = team_block.get("team", {}).get("name", "")
        for group in ("startXI", "substitutes"):
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
