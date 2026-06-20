# src/game/ability_text.py
"""Plain-English 'why this player is good' text for a DraftedAthlete. ZERO pygame.

Turns archetype + stars + the resolved power effects (from powers.py) into a one-line role
read, a list of effect sentences, and a compact card tagline. All human-readable phrasing
lives in powers.json (blurbs + effect_phrasing) -- no English strings are hardcoded here, so
the text rebalances with the data table. Fully unit-tested.

Stars render as ASCII '*' (the pygbag default font ships no star glyph and the existing
widgets already use '*'), so every string returned here is ASCII-safe.
"""
from __future__ import annotations

from src.utils.constants import CONFIG, load_data
from src.game.athlete import DraftedAthlete
from src.game.powers import (this_window_effect, next_window_effect, conversion_for)

_POWERS = load_data(CONFIG["assets"]["powers_file"])
_BLURBS: dict[str, str] = _POWERS.get("blurbs", {})
_PHRASING: dict[str, str] = _POWERS.get("effect_phrasing", {})


def _value_tokens(value: float) -> dict[str, str]:
    """Every placeholder a template might use; str.format ignores the ones it doesn't."""
    return {
        "signed": f"{value:+.1f}",
        "mult": f"{value:.1f}",
        "pct": f"{round(value * 100):+d}%",
        "value": f"{value:.1f}",
    }


def _phrase(effect: dict) -> str:
    """Render one resolved effect ({'kind','value'}) via its template, or '' if unknown."""
    template = _PHRASING.get(effect["kind"], "")
    if not template:
        return ""
    return template.format(**_value_tokens(effect["value"]))


def role_summary(athlete: DraftedAthlete) -> str:
    """One-line role read for the detail panel (archetype blurb; falls back to the code)."""
    return _BLURBS.get(athlete.archetype, athlete.archetype)


def card_tagline(athlete: DraftedAthlete) -> str:
    """Compact this-window effect phrase (no 'This window:' prefix) for the draft card."""
    return _phrase(this_window_effect(athlete))


def effect_lines(athlete: DraftedAthlete) -> list[str]:
    """Detail-panel ability lines: this/next window effects, conversion %, star rating."""
    lines: list[str] = []
    this_text = _phrase(this_window_effect(athlete))
    if this_text:
        lines.append(f"This window: {this_text}")
    next_text = _phrase(next_window_effect(athlete))
    if next_text:
        lines.append(f"Next window: {next_text}")
    lines.append(f"Shot conversion: {round(conversion_for(athlete) * 100)}%")
    lines.append(f"Rating: {'*' * athlete.stars}")
    return lines
