# src/game/statsbomb_adapter.py
"""Pure adapter: StatsBomb open-data events/lineups -> a ReplayFeed simulation script.

No network and no pygame here. The fetching lives in scripts/build_simulation_from_statsbomb.py;
this module only transforms already-parsed JSON (lists of dicts) into the engine's feed schema.

The five engine stat fields (api-field key space, matching src/game/normalize_soccer):
    corner_kicks, shots_on_goal, fouls, goals, cards

NOTE: the live stat menu dropped Saves and added Fouls (Task 1). STAT_FIELDS now matches
that set. _stat_increments still recognises Goal Keeper "Saved" events but emits
goalkeeper_saves, which is no longer a tracked field -- cumulative_timeline silently
ignores any increment not in STAT_FIELDS. Foul-event classification is not yet wired, so
any sim regenerated from StatsBomb open data carries fouls=0 until that is added; bundled
pre-generated sims predate this change and resolve fouls to 0 as well.
"""
import unicodedata

STAT_FIELDS = ("corner_kicks", "shots_on_goal", "fouls", "goals", "cards")

_ON_TARGET = {"Goal", "Saved", "Saved to Post"}


def _ascii_fold(text: str) -> str:
    """Strip accents to keep all generated data pure ASCII (Mbappe, Modric, ...)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def _short_name(full_name: str) -> str:
    """'Kylian Mbappe' -> 'K. Mbappe'; single token returned as-is."""
    parts = _ascii_fold(full_name).split()
    if len(parts) < 2:
        return parts[0] if parts else "Unknown"
    return f"{parts[0][0]}. {parts[-1]}"


def _broad_position(position_name: str) -> str:
    """Map a StatsBomb position name to one of the four engine buckets."""
    p = position_name or ""
    if "Goalkeeper" in p:
        return "Goalkeeper"
    if "Back" in p:                                  # Right Back, Center Back, Wing Back
        return "Defender"
    if "Midfield" in p:
        return "Midfielder"
    if "Forward" in p or "Wing" in p or "Striker" in p:
        return "Attacker"
    return "Midfielder"


def _event_minute(event: dict) -> int:
    return int(event.get("minute", 0))


def _stat_increments(event: dict) -> list[str]:
    """Return the stat fields this single event increments (may be more than one)."""
    etype = event.get("type", {}).get("name", "")
    fields: list[str] = []

    if etype == "Shot":
        outcome = event.get("shot", {}).get("outcome", {}).get("name")
        if outcome in _ON_TARGET:
            fields.append("shots_on_goal")
        if outcome == "Goal":
            fields.append("goals")
    elif etype == "Own Goal For":                    # beneficiary side; counted once
        fields.append("goals")
    elif etype == "Goal Keeper":
        gk = event.get("goalkeeper", {}).get("type", {}).get("name", "")
        if "Saved" in gk:                            # Shot Saved, Shot Saved To Post, ...
            fields.append("goalkeeper_saves")
    elif etype == "Pass":
        if event.get("pass", {}).get("type", {}).get("name") == "Corner":
            fields.append("corner_kicks")
    elif etype == "Foul Committed":
        if event.get("foul_committed", {}).get("card"):
            fields.append("cards")
    elif etype == "Bad Behaviour":
        if event.get("bad_behaviour", {}).get("card"):
            fields.append("cards")

    return fields


def cumulative_timeline(events: list[dict], last_minute: int) -> list[dict]:
    """Build one cumulative snapshot per minute, 0..last_minute inclusive.

    Each snapshot's stats are the match-wide totals observed at or before that minute.
    """
    per_minute: dict[int, dict[str, int]] = {}
    for event in events:
        minute = _event_minute(event)
        for field in _stat_increments(event):
            if field not in STAT_FIELDS:        # e.g. goalkeeper_saves, no longer tracked
                continue
            per_minute.setdefault(minute, {f: 0 for f in STAT_FIELDS})[field] += 1

    snapshots: list[dict] = []
    running = {f: 0 for f in STAT_FIELDS}
    for minute in range(0, last_minute + 1):
        if minute in per_minute:
            for f in STAT_FIELDS:
                running[f] += per_minute[minute][f]
        snapshots.append({"minute": minute, "stats": dict(running)})
    return snapshots


def _last_event_minute(events: list[dict]) -> int:
    return max((_event_minute(e) for e in events), default=0)


def lineups_from_statsbomb(lineup_json: list[dict], starters_only: bool = True) -> list[dict]:
    """Flatten the StatsBomb lineup file into engine-ready athlete rows (ASCII names)."""
    rows: list[dict] = []
    for team_block in lineup_json:
        team_name = _ascii_fold(team_block.get("team_name", ""))
        for player in team_block.get("lineup", []):
            positions = player.get("positions", []) or []
            started = any(pos.get("from") == "00:00" for pos in positions)
            if starters_only and not started:
                continue
            pos_name = positions[0].get("position", "") if positions else ""
            # Prefer the common nickname ("Kylian Mbappe") over the full legal name
            # ("Kylian Mbappe Lottin"), which would otherwise abbreviate wrongly.
            display = player.get("player_nickname") or player.get("player_name", "Unknown")
            rows.append({
                "athlete_id": f"sb-{player.get('player_id')}",
                "name": _short_name(display),
                "broad_position": _broad_position(pos_name),
                "team": team_name,
                "jersey": int(player.get("jersey_number") or 0),
            })
    return rows


def build_simulation(events: list[dict], lineup_json: list[dict], meta: dict) -> dict:
    """Assemble the full ReplayFeed simulation script from parsed StatsBomb JSON."""
    last_minute = _last_event_minute(events)
    return {
        "meta": meta,
        "status_by_minute": [[0, "live"], [last_minute + 1, "finished"]],
        "snapshots": cumulative_timeline(events, last_minute),
        "lineups": lineups_from_statsbomb(lineup_json),
    }
