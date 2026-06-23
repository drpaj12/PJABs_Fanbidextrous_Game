# Live Co-op Dungeon Party Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a 1-3 fighter cooperative party that plays one shared dungeon crawl together, synced through the existing PHP relay, with leader-authoritative window resolution over a live match feed and a per-player economy.

**Architecture:** A pure party model (`src/game/party.py`) owns membership/slots/leader/serialization, the per-player economy split, and the pick->fighter-lines bridge. The relay (`php/soccer_api.php` + `src/sync/relay_client.py`) gains party-aware endpoints that store one canonical, leader-authoritative party JSON blob. A pygame-free coordinator (`src/sync/party_coordinator.py`) drives the sync: every member submits their own loadout (bought with their own gold) and per-window picks; the **leader** alone holds the authoritative `CrawlSession` (from Plan 1b), resolves each window, splits the gold reward, and pushes the canonical dungeon state plus the live match summary and lineup pool. Followers poll and render; they never touch the sports API. The live match feed reuses the existing `FeedClient(is_lead=leader)` + `LiveFeed` + `MatchClock` stack -- only the leader spends API quota, exactly as the single-player live game already does. The party runs in two modes: **SIM** (recorded feed, manual window advance -- fully headless-testable) and **LIVE** (real feed, clock-driven windows).

**Tech Stack:** Python 3.11 (venv at `.venv/Scripts/`), pygame-ce, pygbag/WASM, PHP relay (flat JSON files), `pytest`. Pure game/sync logic stays pygame-free and unit-tested; UI is verified by headless construct smoke; the relay logic is verified by fake-transport unit tests and an in-memory-relay end-to-end smoke.

---

## Locked design decisions (read before implementing)

Confirmed with the product owner. These are deliberate -- do not "improve" them away:

1. **Live feed, leader-fetched and shared.** The leader (username == `config.client.lead_username`, i.e. `drpaj`) runs the only `is_lead` `FeedClient`, which triggers the upstream API-Football fetch via `feed_cache.php?lead=1` (key stays server-side). The leader records snapshots into a `LiveFeed`, then **shares** the derived data with followers by pushing it into the party blob: the live match summary (teams/score/minute/status), the starting-XI **pool** (so followers build the identical shop catalog locally), and every resolved window. **Followers never call the sports API.**
2. **Two timing modes.**
   - **SIM party:** recorded `ReplayFeed`, windows advance **manually** (a Continue tap). Deterministic and headless-testable. This is the smoke/dev path.
   - **LIVE party:** real `LiveFeed`, windows advance on the **real match clock** -- 3 windows per half (0-15', 15-30', 30-45'+extra time; H2 mirrors at 45-60', 60-75', 75-90'+ET), reusing `HalfClock`/`MatchClock` and the half-end-status rule for extra time. The leader resolves each window at its boundary.
3. **Single live half is the core unit; gold spills into a harder H2.** A half (one shop + 3 windows + final %) is a complete session. The full two-half capability is built: gold earned in H1 carries into the H2 shop, and H2 is the engine's existing harder dungeon (deeper gates, tougher monsters, Power carried). H2 is entered when the real match's second half is available (LIVE) or immediately on Continue (SIM).
4. **Per-player economy, independent loadouts.** Each player has their **own** gold pot starting at `economy.base_treasury_per_fighter` (300). Each buys their **own** loadout on their **own** device; the same catalog item (e.g. a "Messi sword") may be bought by all three players as three independent copies. Each window's single gold reward is **split equally** among members (remainder to the lowest slots) and added to each player's pot, carried into the next shop. The leader rebuilds each member's loadout from their reported item_ids purely to compute party gear -- it does **not** re-charge them (the player already paid on their device; coop, non-adversarial).
5. **Rejoin-by-username** (no tokens). An existing username restores its seat/items/gold; a new username takes the next free slot up to 3; else the party is full. Usernames are self-chosen and PII-free.
6. **Fixture selection reuses the existing live picker.** The leader picks the match through the existing `FixtureSelectScreen` -> `LiveResolveScreen` -> `LiveWaitScreen` path (`start_live_select`/`start_live`); the resolved `fixture_id` + kickoff + teams are pushed into the blob so followers share the match context for display.
7. **The existing 2-player room endpoints stay intact.** Party endpoints are *added* alongside them; `tests/test_relay_client.py`'s existing tests keep passing.
8. **`src/sync/session_state.py` is left unused** (vestigial). Party/leader identity lives in `PartyCoordinator`.

---

## File Structure

**Pure game logic (zero pygame, unit-tested in `tests/`):**
- `src/game/party.py` *(create)* -- `Member` (with per-player `treasury`/`ready`), `Party` (membership, slots, leader, full JSON blob incl. `match`/`pool`/`fixture_id`), `join_or_restore`, the pick<->fighter-lines bridge, and `split_gold`.
- `src/game/dungeon.py` *(modify, additive)* -- `DungeonState.to_dict()` / `from_dict()`.
- `src/game/crawl.py` *(modify, additive)* -- `CrawlSession.set_loadout()` (rebuild a member's loadout from item_ids without charging gold).

**Relay (network boundary; client unit-tested with a fake transport, PHP verified structurally):**
- `php/soccer_api.php` *(modify, additive)* -- party file helpers + party actions (`party_join`, `party_state`, `party_pick`, `party_loadout`, `party_push`). The blob carries `match`, `pool`, `fixture_id`, and per-member `treasury`/`items`/`ready`.
- `src/sync/relay_client.py` *(modify, additive)* -- party-aware async methods.

**Sync coordination (pygame-free, fake-relay + fed-LiveFeed testable -- the riskiest logic, isolated here):**
- `src/sync/party_coordinator.py` *(create)* -- `PartyCoordinator`: identity, per-player economy, leader-authoritative resolution + gold split, live-feed ingest + share (match/pool), and the read helpers screens render from.

**UI (pygame; verified by headless construct smoke, NOT pytest):**
- `src/ui/screens/party_screen.py` *(create)* -- Create/Join with a party-number stepper.
- `src/ui/screens/party_lobby_screen.py` *(create)* -- member list; leader's "Start" (SIM) or "Pick match" (LIVE); polls until phase advances.
- `src/ui/screens/party_play_screen.py` *(create)* -- per-member 5-dial editor + Submit; polls until the leader resolves; renders pushed depth/colors/log + live scoreline. Drives manual advance (SIM) or clock advance (LIVE).
- `src/ui/flow.py` *(modify, additive)* -- `DungeonPartyFlow` (SIM and LIVE) + `start_dungeon_party(...)` + `start_dungeon_party_live(...)` + launcher options.
- `src/main.py` *(modify, additive)* -- a `--party` desktop entry argument (SIM party).

**Config:**
- `config/game_config.json` *(modify, additive)* -- a `party` block + `launcher.party_label` / `launcher.party_live_label`.
- `config/layout_config.json` *(modify, additive)* -- `party_*` / `plobby_*` / `pplay_*` geometry keys.

**Tooling / docs:**
- `TOOLS/smoke_party.py` *(create)* -- in-memory relay drives a 3-member two-half SIM crawl end-to-end + draws the three screens headlessly.
- `log.md` *(modify)* -- one completion line.

---

## Canonical party blob

The relay stores and the leader pushes this shape (mirrors `Party.to_dict()`):

```json
{
  "party_id": 0, "leader": "drpaj", "phase": "lobby", "half": 1,
  "fixture_id": 0, "kickoff_iso": "",
  "match": {"home": "", "away": "", "home_goals": 0, "away_goals": 0, "minute": 0, "status": "NS"},
  "pool": [{"athlete_id": 1, "name": "P1", "broad_position": "Attacker", "team": "T", "jersey": 1}],
  "members": [{"username": "drpaj", "slot": 0, "items": [], "treasury": 300, "ready": false, "alive": true, "wounds": 0}],
  "dungeon": null, "log": [], "window_colors": [],
  "resolved_through_window": 0,
  "window_picks": {"0": {"w": 1, "preds": ["goal:1", "shot:3"]}}
}
```

- `phase`: `lobby` -> `shop` -> `play` -> `done`.
- `members[].items`: that player's bought item_ids (== athlete ids); `treasury`: their remaining gold; `ready`: they have finished the current half's shop.
- `pool`: starting-XI rows the leader shares so followers build the identical shop catalog.
- `window_picks[slot]`: that member's picks for window `w` as `"code:line"` strings.

---

## Conventions every task must follow

- **Always use the venv.** Tests: `.venv/Scripts/python -m pytest`. Never bare `python`.
- **Golden rule.** `src/game/` and `src/sync/` import **zero pygame**. `tests/` test only `src/game/` and `src/sync/`. UI is verified by the smoke script.
- **No magic numbers / no globals / type hints on every signature / JSON keys snake_case.**
- **ASCII only** in any `print()`, log line, or `.md` text. pygame *surface* strings may use unicode.
- **Commits go to `main`** (solo dev, no branches). End every commit message with:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
- Use the **Bash tool** (git bash; `&&` works). Quote paths with spaces.
- After each task: tests green, app still launches (where applicable).

---

## Task 1: Config + layout keys

**Files:**
- Modify: `config/game_config.json` (add `party` block; add `launcher.party_label`)
- Modify: `config/layout_config.json` (add `party_*`, `plobby_*`, `pplay_*` keys)

- [x] **Step 1: Add the `party` block to `config/game_config.json`**

Insert a new top-level `"party"` block immediately after the `"client"` block. Insert exactly:

```json
  "party": {
    "_comment": "Cooperative dungeon party (Plan 2). max_size 1-3 fighters; max_rooms party numbers 0..N-1; poll_seconds is how often a client re-reads the canonical party blob from the relay; per_player_treasury is each player's own starting gold pot.",
    "max_size": 3,
    "max_rooms": 4,
    "poll_seconds": 3,
    "per_player_treasury": 300
  },
```

(`per_player_treasury` MUST equal `economy.base_treasury_per_fighter`; it is duplicated here so the party economy reads one obvious key.)

- [x] **Step 2: Add the party launcher labels**

In the `"launcher"` block, after `"dungeon_label"`, add:

```json
    "party_label": "Dungeon party (online)",
    "party_live_label": "Dungeon party (live match)",
```

- [x] **Step 3: Add the layout keys to `config/layout_config.json`**

Before the closing `}` (after the last existing key -- add a comma to it), insert:

```json
  "party_title_size": 30,
  "party_title_y": 110,
  "party_sub_size": 17,
  "party_sub_y": 168,
  "party_num_label_size": 20,
  "party_num_value_size": 40,
  "party_num_y": 250,
  "party_stepper_w": 64,
  "party_stepper_gap": 120,
  "party_btn_w": 320,
  "party_btn_h": 64,
  "party_btn_gap": 20,
  "party_btn_y": 380,
  "plobby_title_size": 28,
  "plobby_title_y": 90,
  "plobby_sub_size": 16,
  "plobby_sub_y": 140,
  "plobby_row_top": 200,
  "plobby_row_h": 56,
  "plobby_row_gap": 10,
  "plobby_row_size": 20,
  "plobby_btn_h": 60,
  "plobby_hint_size": 16,
  "pplay_score_size": 16,
  "pplay_score_y": 38,
  "pplay_wait_size": 20,
  "pplay_wait_y": 420
```

- [x] **Step 4: Verify both files parse**

Run: `.venv/Scripts/python -c "import json;[json.load(open(p,encoding='utf-8')) for p in ['config/game_config.json','config/layout_config.json']];print('OK')"`
Expected: `OK`

- [x] **Step 5: Commit**

```bash
git add config/game_config.json config/layout_config.json
git commit -m "feat(config): party block (economy/poll/rooms) + launcher labels + party layout keys

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Party model -- `Member`, `Party`, serialization

**Files:**
- Create: `src/game/party.py`
- Test: `tests/test_party.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_party.py`:

```python
from src.game.party import Member, Party


def test_create_puts_leader_at_slot_zero_with_default_fields():
    p = Party.create(party_id=2, leader="Drpaj")
    assert p.leader == "drpaj"            # normalized
    assert p.phase == "lobby" and p.half == 1
    assert p.fixture_id == 0 and p.match["status"] == "NS"
    assert len(p.members) == 1
    m = p.members[0]
    assert m.username == "drpaj" and m.slot == 0 and m.treasury == 0 and m.ready is False


def test_round_trips_through_dict():
    p = Party.create(party_id=2, leader="drpaj")
    p.phase = "play"
    p.fixture_id = 12345
    p.match = {"home": "NED", "away": "SWE", "home_goals": 1,
               "away_goals": 0, "minute": 22, "status": "1H"}
    p.pool = [{"athlete_id": 1, "name": "P1", "broad_position": "Attacker",
               "team": "NED", "jersey": 9}]
    p.members[0].items = ["1"]
    p.members[0].treasury = 120
    p.members[0].ready = True
    p.log = ["W1 advance +6"]
    p.window_colors = ["green"]
    p.window_picks = {"0": {"w": 1, "preds": ["goal:1", "shot:3"]}}
    p.dungeon = {"half": 1, "party_size": 1, "depth": 6, "power": 1,
                 "wounds": 0, "threat": 0, "gates_passed": 0, "finished": False}
    again = Party.from_dict(p.to_dict())
    assert again.to_dict() == p.to_dict()
    assert again.members[0].treasury == 120 and again.members[0].ready is True
    assert again.match["home"] == "NED" and again.pool[0]["jersey"] == 9


def test_member_lookup_is_case_insensitive():
    p = Party.create(party_id=0, leader="drpaj")
    assert p.member("DRPAJ") is p.members[0]
    assert p.member("nobody") is None
```

- [x] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.game.party'`

- [x] **Step 3: Implement**

Create `src/game/party.py`:

```python
# src/game/party.py
"""Pure cooperative-party data model: members (each with their own gold pot and loadout),
slots, leader, and the canonical JSON blob the relay stores. Also the per-player gold split
and the bridge from each member's submitted picks to the per-fighter prediction lines the
dungeon resolver consumes. Zero pygame, zero relay I/O."""
from dataclasses import dataclass, field
from typing import Optional

from src.utils.constants import CONFIG, load_data

_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
STAT_CODES: list[str] = [s["code"] for s in _STATS]
DEFAULT_LINES: dict[str, int] = {s["code"]: int(s["default_line"]) for s in _STATS}


def _norm(username: str) -> str:
    return username.strip().lower()


def _empty_match() -> dict:
    return {"home": "", "away": "", "home_goals": 0, "away_goals": 0,
            "minute": 0, "status": "NS"}


@dataclass
class Member:
    username: str
    slot: int
    items: list = field(default_factory=list)   # list[str] item_ids (== athlete ids)
    treasury: int = 0                            # this player's own remaining gold
    ready: bool = False                          # finished the current half's shop
    alive: bool = True
    wounds: int = 0

    def to_dict(self) -> dict:
        return {"username": self.username, "slot": self.slot, "items": list(self.items),
                "treasury": self.treasury, "ready": self.ready,
                "alive": self.alive, "wounds": self.wounds}

    @classmethod
    def from_dict(cls, d: dict) -> "Member":
        return cls(username=str(d["username"]), slot=int(d["slot"]),
                   items=list(d.get("items", [])), treasury=int(d.get("treasury", 0)),
                   ready=bool(d.get("ready", False)), alive=bool(d.get("alive", True)),
                   wounds=int(d.get("wounds", 0)))


@dataclass
class Party:
    party_id: int
    leader: str
    phase: str = "lobby"           # lobby -> shop -> play -> done
    half: int = 1
    fixture_id: int = 0
    kickoff_iso: str = ""
    match: dict = field(default_factory=_empty_match)
    pool: list = field(default_factory=list)            # starting-XI rows shared by leader
    members: list = field(default_factory=list)         # list[Member]
    dungeon: Optional[dict] = None                      # DungeonState.to_dict()
    log: list = field(default_factory=list)
    window_colors: list = field(default_factory=list)
    resolved_through_window: int = 0
    window_picks: dict = field(default_factory=dict)    # {slot_str: {"w": int, "preds": [...]}}

    @classmethod
    def create(cls, party_id: int, leader: str) -> "Party":
        lead = _norm(leader)
        return cls(party_id=int(party_id), leader=lead,
                   members=[Member(username=lead, slot=0)])

    def member(self, username: str) -> Optional[Member]:
        u = _norm(username)
        return next((m for m in self.members if _norm(m.username) == u), None)

    def is_leader(self, username: str) -> bool:
        return _norm(username) == self.leader

    def to_dict(self) -> dict:
        return {
            "party_id": self.party_id, "leader": self.leader, "phase": self.phase,
            "half": self.half, "fixture_id": self.fixture_id, "kickoff_iso": self.kickoff_iso,
            "match": dict(self.match), "pool": [dict(r) for r in self.pool],
            "members": [m.to_dict() for m in self.members],
            "dungeon": self.dungeon, "log": list(self.log),
            "window_colors": list(self.window_colors),
            "resolved_through_window": self.resolved_through_window,
            "window_picks": dict(self.window_picks),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Party":
        return cls(
            party_id=int(d["party_id"]), leader=str(d["leader"]),
            phase=str(d.get("phase", "lobby")), half=int(d.get("half", 1)),
            fixture_id=int(d.get("fixture_id", 0)), kickoff_iso=str(d.get("kickoff_iso", "")),
            match={**_empty_match(), **dict(d.get("match", {}))},
            pool=[dict(r) for r in d.get("pool", [])],
            members=[Member.from_dict(m) for m in d.get("members", [])],
            dungeon=d.get("dungeon"), log=list(d.get("log", [])),
            window_colors=list(d.get("window_colors", [])),
            resolved_through_window=int(d.get("resolved_through_window", 0)),
            window_picks=dict(d.get("window_picks", {})),
        )
```

- [x] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add src/game/party.py tests/test_party.py
git commit -m "feat(party): Member/Party model with per-player economy fields + blob serialization

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Party model -- `join_or_restore`

**Files:**
- Modify: `src/game/party.py`
- Test: `tests/test_party.py`

- [x] **Step 1: Add the failing tests**

Append to `tests/test_party.py`:

```python
def test_new_member_takes_next_free_slot():
    p = Party.create(party_id=0, leader="drpaj")
    assert p.join_or_restore("alice", max_size=3) == (1, True)
    assert p.member("alice").slot == 1
    assert p.join_or_restore("bob", max_size=3) == (2, True)


def test_rejoin_by_username_restores_seat():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("alice", max_size=3)            # slot 1
    assert p.join_or_restore("Alice", max_size=3) == (1, False)   # case-insensitive
    assert len(p.members) == 2


def test_full_party_rejects_new_member_but_admits_existing():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("a", max_size=3)
    p.join_or_restore("b", max_size=3)
    assert p.join_or_restore("c", max_size=3) == (None, False)
    assert len(p.members) == 3
    assert p.join_or_restore("drpaj", max_size=3) == (0, False)
```

- [x] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: FAIL with `AttributeError: 'Party' object has no attribute 'join_or_restore'`

- [x] **Step 3: Implement**

Add this method to the `Party` class (after `is_leader`):

```python
    def join_or_restore(self, username: str, max_size: int) -> tuple[Optional[int], bool]:
        """Rejoin-by-username: an existing member keeps their seat; a new member takes the
        next free slot up to max_size. Returns (slot, is_new); (None, False) when full."""
        existing = self.member(username)
        if existing is not None:
            return existing.slot, False
        if len(self.members) >= int(max_size):
            return None, False
        slot = len(self.members)
        self.members.append(Member(username=_norm(username), slot=slot))
        return slot, True
```

- [x] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: 6 passed

- [x] **Step 5: Commit**

```bash
git add src/game/party.py tests/test_party.py
git commit -m "feat(party): join_or_restore with rejoin-by-username and slot cap

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Party model -- picks bridge + gold split

**Files:**
- Modify: `src/game/party.py`
- Test: `tests/test_party.py`

- [x] **Step 1: Add the failing tests**

Append to `tests/test_party.py`:

```python
from src.game.party import (parse_preds, preds_from_lines, fighter_lines_from_picks,
                            split_gold, DEFAULT_LINES)


def test_parse_and_format_preds_round_trip():
    lines = {"goal": 1, "shot": 3, "corner": 2, "card": 0, "foul": 5}
    preds = preds_from_lines(lines)
    assert "goal:1" in preds and "shot:3" in preds and len(preds) == 5
    assert parse_preds(preds) == lines


def test_parse_preds_drops_unknown_and_malformed():
    assert parse_preds(["goal:2", "bogus:9", "garbage", "shot:x"]) == {"goal": 2}


def test_fighter_lines_orders_by_slot_and_default_fills():
    p = Party.create(party_id=0, leader="drpaj")     # slot 0
    p.join_or_restore("alice", max_size=3)           # slot 1
    p.window_picks = {"1": {"w": 2, "preds": ["goal:3", "shot:9"]}}
    lines = fighter_lines_from_picks(p, window=2)
    assert len(lines) == 2
    assert lines[0] == DEFAULT_LINES                 # slot 0 did not submit
    assert lines[1]["goal"] == 3 and lines[1]["shot"] == 9
    assert lines[1]["corner"] == DEFAULT_LINES["corner"]


def test_fighter_lines_ignores_other_windows():
    p = Party.create(party_id=0, leader="drpaj")
    p.window_picks = {"0": {"w": 1, "preds": ["goal:5"]}}
    assert fighter_lines_from_picks(p, window=2) == [DEFAULT_LINES]


def test_all_picks_in():
    p = Party.create(party_id=0, leader="drpaj")
    p.join_or_restore("alice", max_size=3)
    p.window_picks = {"0": {"w": 1, "preds": ["goal:1"]}}
    assert p.all_picks_in(window=1) is False
    p.window_picks["1"] = {"w": 1, "preds": ["goal:2"]}
    assert p.all_picks_in(window=1) is True


def test_split_gold_is_equal_with_remainder_to_lowest_slots():
    assert split_gold(90, 3) == [30, 30, 30]
    assert split_gold(100, 3) == [34, 33, 33]   # remainder 1 -> slot 0
    assert split_gold(7, 1) == [7]
    assert split_gold(5, 0) == []
```

- [x] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: FAIL with `ImportError: cannot import name 'parse_preds'`

- [x] **Step 3: Implement**

Add these module-level functions to the end of `src/game/party.py`:

```python
def parse_preds(preds: list) -> dict:
    """["goal:1", "shot:3"] -> {"goal": 1, "shot": 3}. Unknown codes and malformed tokens
    are dropped (picks arrive over the wire)."""
    out: dict = {}
    for token in preds:
        if not isinstance(token, str) or ":" not in token:
            continue
        code, _, raw = token.partition(":")
        if code not in STAT_CODES:
            continue
        try:
            out[code] = int(raw)
        except (TypeError, ValueError):
            continue
    return out


def preds_from_lines(lines: dict) -> list:
    """Inverse of parse_preds: a stable "code:line" list for every known stat."""
    return [f"{code}:{int(lines.get(code, DEFAULT_LINES[code]))}" for code in STAT_CODES]


def fighter_lines_from_picks(party: "Party", window: int) -> list:
    """One prediction-line dict per member, ordered by slot. A member who has not submitted
    (or submitted partial) picks for `window` is filled from DEFAULT_LINES so the leader can
    always resolve."""
    out: list = []
    for member in sorted(party.members, key=lambda m: m.slot):
        entry = party.window_picks.get(str(member.slot))
        submitted = parse_preds(entry["preds"]) if entry and int(entry.get("w", -1)) == window else {}
        out.append({**DEFAULT_LINES, **submitted})
    return out


def split_gold(total: int, n: int) -> list:
    """Split a single gold reward equally among n members; any remainder goes to the lowest
    slots first. split_gold(100, 3) -> [34, 33, 33]."""
    if n <= 0:
        return []
    share, rem = divmod(int(total), n)
    return [share + (1 if i < rem else 0) for i in range(n)]
```

Add this method to the `Party` class (after `join_or_restore`):

```python
    def all_picks_in(self, window: int) -> bool:
        """True when every member has submitted picks for `window`."""
        return all(
            (entry := self.window_picks.get(str(m.slot))) is not None
            and int(entry.get("w", -1)) == window
            for m in self.members)
```

- [x] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_party.py -q`
Expected: 12 passed

- [x] **Step 5: Commit**

```bash
git add src/game/party.py tests/test_party.py
git commit -m "feat(party): picks<->fighter-lines bridge, all_picks_in, equal gold split

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `DungeonState` serialization

**Files:**
- Modify: `src/game/dungeon.py`
- Test: `tests/test_dungeon.py`

- [x] **Step 1: Add the failing test**

Append to `tests/test_dungeon.py`:

```python
def test_dungeon_state_round_trips_through_dict():
    from src.game.dungeon import DungeonState
    st = DungeonState(half=2, party_size=3, depth=11, power=4, wounds=1,
                      threat=2, gates_passed=2, finished=False)
    again = DungeonState.from_dict(st.to_dict())
    assert again.to_dict() == st.to_dict()
    assert again.total_tiles == st.total_tiles
```

(If `DungeonState`'s real constructor field names differ -- check `src/game/dungeon.py` -- mirror them exactly in the test and the methods.)

- [x] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon.py::test_dungeon_state_round_trips_through_dict -q`
Expected: FAIL with `AttributeError: type object 'DungeonState' has no attribute 'from_dict'`

- [x] **Step 3: Implement**

In `src/game/dungeon.py`, add to the `DungeonState` dataclass (after the `total_tiles` property). Adjust the field list to match the real dataclass fields:

```python
    def to_dict(self) -> dict:
        return {"half": self.half, "party_size": self.party_size, "depth": self.depth,
                "power": self.power, "wounds": self.wounds, "threat": self.threat,
                "gates_passed": self.gates_passed, "finished": self.finished}

    @classmethod
    def from_dict(cls, d: dict) -> "DungeonState":
        return cls(half=int(d["half"]), party_size=int(d["party_size"]),
                   depth=int(d.get("depth", 0)), power=int(d.get("power", 0)),
                   wounds=int(d.get("wounds", 0)), threat=int(d.get("threat", 0)),
                   gates_passed=int(d.get("gates_passed", 0)),
                   finished=bool(d.get("finished", False)))
```

- [x] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_dungeon.py -q`
Expected: all dungeon tests pass.

- [x] **Step 5: Commit**

```bash
git add src/game/dungeon.py tests/test_dungeon.py
git commit -m "feat(dungeon): DungeonState.to_dict/from_dict for party serialization

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `CrawlSession.set_loadout`

**Files:**
- Modify: `src/game/crawl.py`
- Test: `tests/test_crawl.py`

The leader mirrors what each player bought on their own device (with their own gold) so it can compute party gear. It rebuilds the loadout from item_ids, enforcing structural rules (slot cap, two-handed) but **not** charging the treasury. Independent per-player purchasing means the same item_id can appear in different members' loadouts -- that is fine because each member has their own `Loadout`.

- [x] **Step 1: Inspect the test file's pool helper**

Open `tests/test_crawl.py` and find how the existing tests build a pool and a `CrawlSession` (the helper name, e.g. `_pool()`, and `DraftedAthlete` construction). Use that exact helper in the new tests below; if it is named differently, substitute the real name.

- [x] **Step 2: Add the failing tests**

Append to `tests/test_crawl.py`:

```python
def test_set_loadout_rebuilds_from_item_ids_without_charging_gold():
    import random
    from src.game.crawl import CrawlSession
    pool = _pool()
    session = CrawlSession(party_size=2, pool=pool, rng=random.Random(99))
    treasury_before = session.treasury
    catalog = session.catalog()
    weapon = next(it for it in catalog if it.category == "weapon")
    armor = next(it for it in catalog if it.category == "armor")
    notes = session.set_loadout(0, [weapon.item_id, armor.item_id])
    assert {it.item_id for it in session.loadouts[0].items} == {weapon.item_id, armor.item_id}
    assert session.treasury == treasury_before        # gold NOT touched
    assert notes == []
    # the SAME weapon can be given to another member (independent loadouts)
    session.set_loadout(1, [weapon.item_id])
    assert session.loadouts[1].items[0].item_id == weapon.item_id


def test_set_loadout_skips_unknown_items_with_a_note():
    import random
    from src.game.crawl import CrawlSession
    session = CrawlSession(party_size=1, pool=_pool(), rng=random.Random(1))
    notes = session.set_loadout(0, ["does-not-exist"])
    assert session.loadouts[0].items == []
    assert any("unknown" in n.lower() for n in notes)
```

- [x] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_crawl.py::test_set_loadout_rebuilds_from_item_ids_without_charging_gold -q`
Expected: FAIL with `AttributeError: 'CrawlSession' object has no attribute 'set_loadout'`

- [x] **Step 4: Implement**

Add this method to `CrawlSession` (in the `-- shop --` section, after `sell`):

```python
    def set_loadout(self, member: int, item_ids: list) -> list:
        """Rebuild a member's loadout from item_ids -- the leader mirrors what a player bought
        on their own device with their own gold. Structural rules (slot cap, two-handed) are
        enforced; affordability is NOT (the player already paid client-side). Returns ASCII
        notes for any item that could not be placed."""
        catalog_by_id = {it.item_id: it for it in self.catalog()}
        loadout = Loadout()
        notes: list = []
        for item_id in item_ids:
            item = catalog_by_id.get(item_id)
            if item is None:
                notes.append(f"slot {member}: unknown item {item_id}")
                continue
            ok, reason = loadout.can_add(item)
            if ok:
                loadout.add(item)
            else:
                notes.append(f"slot {member}: skipped {item.name} ({reason})")
        self.loadouts[member] = loadout
        return notes
```

(Confirm `Loadout` is imported in `crawl.py` and that `loadout.can_add`/`add` are its real methods -- they are used by `buy`. Mirror `buy`'s usage exactly.)

- [x] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_crawl.py -q`
Expected: all crawl tests pass (existing + the two new ones).

- [x] **Step 6: Commit**

```bash
git add src/game/crawl.py tests/test_crawl.py
git commit -m "feat(crawl): CrawlSession.set_loadout rebuilds member gear without charging gold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Relay client -- party methods

**Files:**
- Modify: `src/sync/relay_client.py`
- Test: `tests/test_relay_client.py`

Reads (`party_state`) are GET; writes are POST with a JSON body carrying a `type`. The existing room tests must keep passing.

- [x] **Step 1: Inspect the existing client + test helpers**

Open `src/sync/relay_client.py` and `tests/test_relay_client.py`. Note: the class name (`RelayClient`), the transport attribute names (`self._base`/`self._path`/`self._t` or similar), the fake-transport helper in the test (e.g. `_FakeTransport` with `.posts`/`.gets`), how existing room methods build URLs and bodies, and which `import` provides `json`/`Any`. Mirror those exactly in Steps 2-3; substitute real names where they differ.

- [x] **Step 2: Add the failing tests**

Append to `tests/test_relay_client.py` (adapt `RelayClient`/`_FakeTransport` to the real names found in Step 1):

```python
def test_party_join_uses_action_party_and_username():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_join(party=2, username="drpaj"))
    url, body = t.posts[0]
    assert "action=party_join" in url and "party=2" in url
    assert '"type": "party_join"' in body and "drpaj" in body


def test_party_state_is_a_get():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_state(party=1))
    assert "action=party_state" in t.gets[0] and "party=1" in t.gets[0]


def test_party_pick_carries_window_and_preds():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_pick(party=0, username="a", window=2, preds=["goal:1", "shot:3"]))
    url, body = t.posts[0]
    assert "action=party_pick" in url
    assert '"window": 2' in body and "goal:1" in body


def test_party_loadout_carries_items_and_treasury():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_loadout(party=0, username="a", item_ids=["1"], treasury=120))
    body = t.posts[0][1]
    assert '"type": "party_loadout"' in body and '"treasury": 120' in body and '"1"' in body


def test_party_push_carries_arbitrary_state():
    t = _FakeTransport()
    client = RelayClient(base_url="http://x", transport=t)
    asyncio.run(client.party_push(party=0, username="drpaj",
                                  state={"phase": "play", "clear_picks": True}))
    body = t.posts[0][1]
    assert '"type": "party_push"' in body and '"phase": "play"' in body and '"clear_picks": true' in body
```

- [x] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_relay_client.py -q`
Expected: the five new tests FAIL (`AttributeError: ... 'party_join'`); the existing room tests pass.

- [x] **Step 4: Implement**

In `src/sync/relay_client.py`, add a party URL builder and methods to `RelayClient` (after the last existing method). Use the real attribute names from Step 1:

```python
    def _party_url(self, action: str, party: int) -> str:
        return f"{self._base}{self._path}?action={action}&party={party}"

    async def party_join(self, party: int, username: str) -> dict[str, Any]:
        body = json.dumps({"type": "party_join", "username": username})
        return json.loads(await self._t.post(self._party_url("party_join", party), body))

    async def party_state(self, party: int) -> dict[str, Any]:
        return json.loads(await self._t.get(self._party_url("party_state", party)))

    async def party_pick(self, party: int, username: str, window: int,
                         preds: list[str]) -> dict[str, Any]:
        body = json.dumps({"type": "party_pick", "username": username,
                           "window": window, "preds": preds})
        return json.loads(await self._t.post(self._party_url("party_pick", party), body))

    async def party_loadout(self, party: int, username: str, item_ids: list[str],
                            treasury: int) -> dict[str, Any]:
        body = json.dumps({"type": "party_loadout", "username": username,
                           "item_ids": item_ids, "treasury": treasury})
        return json.loads(await self._t.post(self._party_url("party_loadout", party), body))

    async def party_push(self, party: int, username: str,
                         state: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"type": "party_push", "username": username, **state})
        return json.loads(await self._t.post(self._party_url("party_push", party), body))
```

- [x] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_relay_client.py -q`
Expected: all pass (existing room tests + 5 new).

- [x] **Step 6: Commit**

```bash
git add src/sync/relay_client.py tests/test_relay_client.py
git commit -m "feat(relay-client): party_join/state/pick/loadout/push methods

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: PHP relay -- party actions

**Files:**
- Modify: `php/soccer_api.php`

No pytest (no PHP runtime assumed). Verify with `php -l` if available; otherwise the Task 15 in-memory smoke covers the protocol shape the client relies on. The blob mirrors `Party.to_dict()` (Task 2).

- [x] **Step 1: Inspect the existing PHP structure**

Open `php/soccer_api.php`. Note the existing helper names (`ROOMS_DIR`, `respond()`, `fail()`, the dispatcher `switch ($action)` block, how `$_GET` params are read). Mirror those exactly. Keep all existing room actions untouched.

- [x] **Step 2: Add party file helpers**

After the existing room helpers, add:

```php
define('MAX_PARTIES', 4);
define('PARTY_MAX_SIZE', 3);

function get_party_path(int $party): string { return ROOMS_DIR . "party_$party.json"; }

function read_party(int $party): ?array {
    $path = get_party_path($party);
    if (!file_exists($path)) { return null; }
    $c = file_get_contents($path);
    return $c === false ? null : json_decode($c, true);
}

function write_party(int $party, array $data): bool {
    $data['updated_at'] = time();
    return file_put_contents(get_party_path($party),
        json_encode($data, JSON_PRETTY_PRINT), LOCK_EX) !== false;
}

function norm_user(string $u): string { return strtolower(trim($u)); }

function create_empty_party(int $party, string $leader): array {
    return [
        'party_id' => $party, 'leader' => $leader, 'phase' => 'lobby', 'half' => 1,
        'fixture_id' => 0, 'kickoff_iso' => '',
        'match' => ['home' => '', 'away' => '', 'home_goals' => 0, 'away_goals' => 0,
                    'minute' => 0, 'status' => 'NS'],
        'pool' => [],
        'members' => [['username' => $leader, 'slot' => 0, 'items' => [],
                       'treasury' => 0, 'ready' => false, 'alive' => true, 'wounds' => 0]],
        'dungeon' => null, 'log' => [], 'window_colors' => [],
        'resolved_through_window' => 0, 'window_picks' => (object)[],
    ];
}

function party_member_index(array $p, string $user): int {
    foreach ($p['members'] as $i => $m) {
        if (norm_user($m['username']) === $user) { return $i; }
    }
    return -1;
}
```

- [x] **Step 3: Add the five party action handlers**

After the existing action functions, add:

```php
function action_party_join(int $party): void {
    if ($party < 0 || $party >= MAX_PARTIES) { fail('Invalid party number'); }
    $input = json_decode(file_get_contents('php://input'), true);
    $user = norm_user($input['username'] ?? '');
    if ($user === '') { fail('Missing username'); }
    $p = read_party($party);
    if (!$p) {
        $p = create_empty_party($party, $user);
        write_party($party, $p);
        respond(['success' => true, 'slot' => 0, 'is_leader' => true]);
    }
    $idx = party_member_index($p, $user);
    if ($idx >= 0) {
        respond(['success' => true, 'slot' => (int)$p['members'][$idx]['slot'],
                 'is_leader' => ($user === norm_user($p['leader']))]);
    }
    if (count($p['members']) >= PARTY_MAX_SIZE) { fail('Party is full', 409); }
    $slot = count($p['members']);
    $p['members'][] = ['username' => $user, 'slot' => $slot, 'items' => [],
                       'treasury' => 0, 'ready' => false, 'alive' => true, 'wounds' => 0];
    write_party($party, $p);
    respond(['success' => true, 'slot' => $slot, 'is_leader' => false]);
}

function action_party_state(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    respond(['success' => true, 'party' => $p]);
}

function action_party_pick(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);
    $idx = party_member_index($p, norm_user($input['username'] ?? ''));
    if ($idx < 0) { fail('Not a member', 403); }
    $slot = (string)$p['members'][$idx]['slot'];
    $picks = (array)($p['window_picks'] ?? []);
    $picks[$slot] = ['w' => (int)($input['window'] ?? 0),
                     'preds' => array_values((array)($input['preds'] ?? []))];
    $p['window_picks'] = $picks;
    write_party($party, $p);
    respond(['success' => true]);
}

function action_party_loadout(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);
    $idx = party_member_index($p, norm_user($input['username'] ?? ''));
    if ($idx < 0) { fail('Not a member', 403); }
    $p['members'][$idx]['items'] = array_values((array)($input['item_ids'] ?? []));
    $p['members'][$idx]['treasury'] = (int)($input['treasury'] ?? 0);
    $p['members'][$idx]['ready'] = true;
    write_party($party, $p);
    respond(['success' => true]);
}

function action_party_push(int $party): void {
    $p = read_party($party);
    if (!$p) { fail('Party not found', 404); }
    $input = json_decode(file_get_contents('php://input'), true);
    if (norm_user($input['username'] ?? '') !== norm_user($p['leader'])) {
        fail('Only the leader may push state', 403);
    }
    foreach (['phase', 'half', 'fixture_id', 'kickoff_iso', 'match', 'pool', 'members',
              'dungeon', 'log', 'window_colors', 'resolved_through_window'] as $key) {
        if (array_key_exists($key, $input)) { $p[$key] = $input[$key]; }
    }
    if (!empty($input['clear_picks'])) { $p['window_picks'] = (object)[]; }
    write_party($party, $p);
    respond(['success' => true]);
}
```

- [x] **Step 4: Wire the actions into the dispatcher**

Where `$_GET` params are read near the dispatcher, add:

```php
$party = isset($_GET['party']) ? intval($_GET['party']) : -1;
```

Add these cases to `switch ($action)`:

```php
    case 'party_join': action_party_join($party); break;
    case 'party_state': action_party_state($party); break;
    case 'party_pick': action_party_pick($party); break;
    case 'party_loadout': action_party_loadout($party); break;
    case 'party_push': action_party_push($party); break;
```

If the `case ''` info action lists endpoints, add the new actions there too.

- [x] **Step 5: Verify PHP syntax**

Run: `command -v php >/dev/null 2>&1 && php -l "php/soccer_api.php" || echo "php not installed -- structural review only"`
Expected: `No syntax errors detected ...` (or the skip message). Fix any reported error before committing.

- [x] **Step 6: Commit**

```bash
git add php/soccer_api.php
git commit -m "feat(relay): party_join/state/pick/loadout/push endpoints (per-player economy blob)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `PartyCoordinator` (leader-authoritative sync + economy)

**Files:**
- Create: `src/sync/party_coordinator.py`
- Test: `tests/test_party_coordinator.py`

The crux: pygame-free, relay-driven coordination + per-player economy. Fully testable with an in-memory fake relay and a stub actuals function. The leader alone holds the authoritative `CrawlSession`; `actuals_fn(window)` returns that window's actuals dict (the flow builds it from whichever feed is active -- recorded in SIM, live in LIVE).

- [x] **Step 1: Confirm the score helpers exist**

Check `src/game/score.py` for `percent_complete` and `total_tiles_game` (used by `view()`). If their names differ, note the real names and use them in Step 3 (the single-player dungeon final screen already computes percent + total tiles -- reuse whatever it calls).

- [x] **Step 2: Write the failing test**

Create `tests/test_party_coordinator.py`:

```python
import asyncio

from src.game.athlete import DraftedAthlete
from src.game.party import Party
from src.sync.party_coordinator import PartyCoordinator


class FakeRelay:
    """In-memory stand-in for RelayClient with the same async party_* surface."""
    def __init__(self):
        self.blob = None

    async def party_join(self, party, username):
        if self.blob is None:
            self.blob = Party.create(party, leader=username).to_dict()
            return {"success": True, "slot": 0, "is_leader": True}
        p = Party.from_dict(self.blob)
        slot, _ = p.join_or_restore(username, max_size=3)
        self.blob = p.to_dict()
        return {"success": True, "slot": slot, "is_leader": p.is_leader(username)}

    async def party_state(self, party):
        return {"success": True, "party": self.blob}

    async def party_pick(self, party, username, window, preds):
        p = Party.from_dict(self.blob)
        p.window_picks[str(p.member(username).slot)] = {"w": window, "preds": preds}
        self.blob = p.to_dict()
        return {"success": True}

    async def party_loadout(self, party, username, item_ids, treasury):
        p = Party.from_dict(self.blob)
        m = p.member(username)
        m.items, m.treasury, m.ready = item_ids, treasury, True
        self.blob = p.to_dict()
        return {"success": True}

    async def party_push(self, party, username, state):
        d = dict(self.blob)
        if state.pop("clear_picks", False):
            d["window_picks"] = {}
        d.update(state)
        self.blob = d
        return {"success": True}


def _pool(n=22):
    cats = ["Attacker", "Defender", "Midfielder", "Goalkeeper"]
    return [DraftedAthlete.create(athlete_id=i, name=f"P{i}", broad_position=cats[i % 4],
            team="T", jersey=i) for i in range(1, n + 1)]


def _actuals(_w):
    return {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}


def _coord(relay, username, pool):
    return PartyCoordinator(relay=relay, party_id=0, username=username,
                            pool=pool, actuals_fn=_actuals)


def _join_all(*coords):
    for c in coords:
        asyncio.run(c.join())


def test_join_assigns_leader_and_seeds_starting_gold_on_shop():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    assert lead.is_leader and not a.is_leader
    asyncio.run(lead.leader_start())            # lobby -> shop, seed each pot
    asyncio.run(a.refresh())
    assert a.shop_budget() == 300 and lead.shop_budget() == 300


def test_full_window_round_trip_resolves_and_followers_see_depth():
    relay, pool = FakeRelay(), _pool()
    lead, a, b = (_coord(relay, "drpaj", pool), _coord(relay, "alice", pool),
                  _coord(relay, "bob", pool))
    _join_all(lead, a, b)
    asyncio.run(lead.leader_start())
    for c in (lead, a, b):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, a, b):
        asyncio.run(c.refresh())
    assert lead.phase() == "play" and a.phase() == "play"
    assert lead.session.party_size == 3
    for c in (lead, a, b):
        asyncio.run(c.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    for c in (a, b):
        asyncio.run(c.refresh())
    assert lead.resolved_through() == 1 and b.resolved_through() == 1
    assert b.view()["depth"] > 0 and b.view()["depth"] == lead.view()["depth"]


def test_window_gold_is_split_into_each_players_pot():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_pick(1, {"goal": 1, "shot": 3, "corner": 3, "card": 1, "foul": 4}))
    asyncio.run(lead.refresh())
    asyncio.run(lead.leader_try_resolve(1))
    asyncio.run(a.refresh())
    # each player's pot grew by an equal share of the window gold
    assert a.my_treasury() >= 300 and lead.my_treasury() >= 300
    assert (a.my_treasury() - 300) + (lead.my_treasury() - 300) == lead.last_gold


def test_leader_resolves_with_force_when_a_follower_did_not_submit():
    relay, pool = FakeRelay(), _pool()
    lead, a = _coord(relay, "drpaj", pool), _coord(relay, "alice", pool)
    _join_all(lead, a)
    asyncio.run(lead.leader_start())
    for c in (lead, a):
        asyncio.run(c.refresh())
        asyncio.run(c.submit_loadout([], c.shop_budget()))
    asyncio.run(lead.leader_try_reconcile_shop())
    asyncio.run(lead.refresh())
    asyncio.run(lead.submit_pick(1, {"goal": 1}))    # only the leader submitted
    asyncio.run(lead.refresh())
    assert asyncio.run(lead.leader_try_resolve(1, require_all=True)) is False   # blocked
    assert asyncio.run(lead.leader_try_resolve(1, require_all=False)) is True   # forced
    assert lead.resolved_through() == 1
```

- [x] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_party_coordinator.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.sync.party_coordinator'`

- [x] **Step 4: Implement**

Create `src/sync/party_coordinator.py` (use the real `score.py` helper names from Step 1):

```python
# src/sync/party_coordinator.py
"""Leader-authoritative party sync + per-player economy, free of pygame and of any concrete
transport.

Every client constructs one PartyCoordinator. All clients submit their own loadout (bought
with their own gold pot) and per-window picks; the LEADER alone holds the authoritative
CrawlSession, reconciles the shop, resolves each window, splits the gold reward equally into
each player's pot, and pushes the canonical dungeon state (plus the live match summary and
lineup pool). Followers only read (`refresh`) and render (`view`).

The relay object needs only the async party_* methods (RelayClient in production, an in-memory
fake in tests). actuals_fn(window) -> per-window actuals dict is supplied by the flow (built
from the recorded feed in SIM, the live feed in LIVE)."""
import random
from typing import Callable, Optional

from src.game.crawl import CrawlSession
from src.game.party import (Party, fighter_lines_from_picks, preds_from_lines, split_gold)
from src.game.score import percent_complete, total_tiles_game
from src.utils.constants import CONFIG

_PARTY = CONFIG["party"]
_MAX_SIZE = int(_PARTY["max_size"])
_PER_PLAYER = int(_PARTY["per_player_treasury"])
_MAX_WOUNDS = int(CONFIG["dungeon"]["max_wounds"])


class PartyCoordinator:
    def __init__(self, relay, party_id: int, username: str, pool: list,
                 actuals_fn: Callable[[int], dict], seed: Optional[int] = None) -> None:
        self.relay = relay
        self.party_id = int(party_id)
        self.username = username
        self.pool = pool
        self.actuals_fn = actuals_fn
        self.seed = int(seed if seed is not None else CONFIG["game"]["rng_seed"])
        self.slot: int = -1
        self.is_leader: bool = False
        self.party: Optional[Party] = None
        self.session: Optional[CrawlSession] = None   # authoritative, leader only
        self.last_gold: int = 0                       # gold from the most recent resolution

    # -- identity / read -----------------------------------------------------
    async def join(self) -> None:
        resp = await self.relay.party_join(self.party_id, self.username)
        self.slot = int(resp.get("slot", -1))
        self.is_leader = bool(resp.get("is_leader", False))
        await self.refresh()

    async def refresh(self) -> None:
        resp = await self.relay.party_state(self.party_id)
        blob = resp.get("party")
        if blob:
            self.party = Party.from_dict(blob)

    def phase(self) -> str:
        return self.party.phase if self.party else "lobby"

    def half(self) -> int:
        return self.party.half if self.party else 1

    def resolved_through(self) -> int:
        return self.party.resolved_through_window if self.party else 0

    def me(self):
        return self.party.member(self.username) if self.party else None

    def my_treasury(self) -> int:
        m = self.me()
        return m.treasury if m else 0

    def shop_budget(self) -> int:
        """Gold this player may spend in the current shop: their own pot (seeded to
        per_player_treasury for H1, carried remainder + earned gold for H2)."""
        return self.my_treasury()

    def view(self) -> dict:
        """Everything a screen needs to render the current dungeon + match (any client)."""
        p = self.party
        d = (p.dungeon if p and p.dungeon else {})
        size = len(p.members) if p else 1
        cleared_prev = self.session.cleared_prev_halves if self.session else 0
        depth = int(d.get("depth", 0))
        return {
            "depth": depth,
            "total": int(total_tiles_game(size)),
            "power": int(d.get("power", 0)),
            "wounds": int(d.get("wounds", 0)),
            "log": list(p.log if p else []),
            "window_colors": list(p.window_colors if p else []),
            "members": [(m.username, m.treasury) for m in p.members] if p else [],
            "match": dict(p.match) if p else {},
            "percent": percent_complete(depth + cleared_prev, size) if p else 0,
        }

    # -- member writes -------------------------------------------------------
    async def submit_loadout(self, item_ids: list, treasury: int) -> None:
        await self.relay.party_loadout(self.party_id, self.username, item_ids, int(treasury))

    async def submit_pick(self, window: int, lines: dict) -> None:
        await self.relay.party_pick(self.party_id, self.username, window,
                                    preds_from_lines(lines))

    # -- leader-authoritative actions ---------------------------------------
    async def leader_start(self) -> None:
        """Lobby -> shop: seed each member's own starting gold pot."""
        if not self.is_leader or self.party is None:
            return
        members = []
        for m in self.party.members:
            d = m.to_dict()
            d["treasury"] = _PER_PLAYER
            d["ready"] = False
            members.append(d)
        await self.relay.party_push(self.party_id, self.username,
                                    {"phase": "shop", "members": members})
        await self.refresh()

    async def leader_try_reconcile_shop(self) -> bool:
        """Once every member is `ready`, build the authoritative session and mirror each
        member's bought loadout into it (no gold charge), then push phase=play. Idempotent
        while phase=='shop'."""
        if not self.is_leader or self.party is None or self.party.phase != "shop":
            return False
        if not all(m.ready for m in self.party.members):
            return False
        self._build_session()
        for m in sorted(self.party.members, key=lambda x: x.slot):
            self.session.set_loadout(m.slot, m.items)
        await self.relay.party_push(self.party_id, self.username, {"phase": "play"})
        await self.refresh()
        return True

    async def leader_try_resolve(self, window: int, require_all: bool = True) -> bool:
        """Resolve `window` and push the new dungeon state + split gold. With require_all the
        leader waits until every member has submitted; with require_all=False (a clock/Continue
        boundary) it resolves now, default-filling absent members. Returns True when it pushed."""
        if not self.is_leader or self.party is None or self.party.phase != "play":
            return False
        if self.party.resolved_through_window >= window:
            return False
        if require_all and not self.party.all_picks_in(window):
            return False
        self._build_session()
        fighter_lines = fighter_lines_from_picks(self.party, window)
        label = f"H{self.session.half} W{window}"
        result = self.session.resolve_window(fighter_lines, self.actuals_fn(window), label)
        self.last_gold = result.gold
        await self._push_after_resolve(window)
        return True

    async def leader_advance_half(self) -> None:
        """After H1's windows: into the H2 shop (keep each player's carried gold, clear ready
        + picks). After H2: phase=done."""
        if not self.is_leader or self.session is None:
            return
        if self.session.half == 1:
            self.session.begin_second_half()
            members = []
            for m in self.party.members:
                d = m.to_dict()
                d["ready"] = False
                members.append(d)
            await self.relay.party_push(self.party_id, self.username, {
                "phase": "shop", "half": 2, "resolved_through_window": 0,
                "members": members, "clear_picks": True})
        else:
            await self.relay.party_push(self.party_id, self.username, {"phase": "done"})
        await self.refresh()

    async def leader_share_match(self, match: dict, pool_rows: Optional[list] = None,
                                 fixture_id: Optional[int] = None,
                                 kickoff_iso: Optional[str] = None) -> None:
        """LIVE only: the leader pushes the live match summary it fetched, plus (once) the
        starting-XI pool followers build their shop catalog from."""
        if not self.is_leader or self.party is None:
            return
        state: dict = {"match": match}
        if pool_rows is not None:
            state["pool"] = pool_rows
        if fixture_id is not None:
            state["fixture_id"] = int(fixture_id)
        if kickoff_iso is not None:
            state["kickoff_iso"] = kickoff_iso
        await self.relay.party_push(self.party_id, self.username, state)
        await self.refresh()

    # -- internals -----------------------------------------------------------
    def _build_session(self) -> None:
        if self.session is None:
            self.session = CrawlSession(party_size=len(self.party.members),
                                        pool=self.pool, rng=random.Random(self.seed))

    async def _push_after_resolve(self, window: int) -> None:
        s = self.session
        shares = split_gold(self.last_gold, len(self.party.members))
        members = []
        for m in sorted(self.party.members, key=lambda x: x.slot):
            d = m.to_dict()
            d["treasury"] = m.treasury + shares[m.slot]
            d["wounds"] = s.state.wounds
            d["alive"] = s.state.wounds < _MAX_WOUNDS
            members.append(d)
        await self.relay.party_push(self.party_id, self.username, {
            "dungeon": s.state.to_dict(), "log": list(s.log),
            "window_colors": list(s.window_colors), "members": members,
            "resolved_through_window": window, "clear_picks": True})
        await self.refresh()
```

- [x] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_party_coordinator.py -q`
Expected: 4 passed.

Then the full pure suite:
Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add src/sync/party_coordinator.py tests/test_party_coordinator.py
git commit -m "feat(sync): PartyCoordinator leader-authoritative sync + per-player gold split

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: `PartyScreen` (Create / Join)

**Files:**
- Create: `src/ui/screens/party_screen.py`

pygame; verified by construction. Username comes from upstream `UsernameScreen`. `on_done(party_number: int)` fires for both buttons (the relay's `party_join` is create-or-join). SIM auto-proceeds with party 0.

- [x] **Step 1: Confirm widget + color names**

Open `src/ui/widgets.py` (or wherever `Button`/`font` live -- see imports in `dungeon_play_screen.py`) and `config/layout_config.json`. Confirm `Button`, `font`, `Screen` base, and the body-text size key used by other screens (e.g. a `ui_*` size). Use the real names in Step 2.

- [x] **Step 2: Write the screen**

Create `src/ui/screens/party_screen.py`:

```python
# src/ui/screens/party_screen.py
"""Create Party / Join Party. A party number (0..max_rooms-1) chosen with a -/+ stepper and
shared out-of-band; the username comes from the upstream UsernameScreen. Both buttons call
on_done(party_number) -- party_join is create-or-join. SIM auto-creates party 0."""
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_MAX_ROOMS = int(CONFIG["party"]["max_rooms"])


class PartyScreen(Screen):
    def __init__(self, app: "App", username: str, on_done: Callable[[int], None],
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.username = username
        self.on_done = on_done
        self.sim = sim
        self.party_number = 0
        self._done = False
        sw = app.screen.get_width()
        bw, bh = LAYOUT.i("party_btn_w", 320), LAYOUT.i("party_btn_h", 64)
        gap, y = LAYOUT.i("party_btn_gap", 20), LAYOUT.i("party_btn_y", 380)
        x = (sw - bw) // 2
        self.create_btn = Button(pygame.Rect(x, y, bw, bh), "Create Party")
        self.join_btn = Button(pygame.Rect(x, y + bh + gap, bw, bh), "Join Party")
        sttop = LAYOUT.i("party_num_y", 250)
        stw, stgap = LAYOUT.i("party_stepper_w", 64), LAYOUT.i("party_stepper_gap", 120)
        cx = sw // 2
        self.minus_btn = Button(pygame.Rect(cx - stgap, sttop, stw, stw), "-")
        self.plus_btn = Button(pygame.Rect(cx + stgap - stw, sttop, stw, stw), "+")

    def handle(self, event: pygame.event.Event) -> None:
        if self._done or event.type != pygame.MOUSEBUTTONDOWN:
            return
        if self.minus_btn.hit(event.pos):
            self.party_number = (self.party_number - 1) % _MAX_ROOMS
        elif self.plus_btn.hit(event.pos):
            self.party_number = (self.party_number + 1) % _MAX_ROOMS
        elif self.create_btn.hit(event.pos) or self.join_btn.hit(event.pos):
            self._finish()

    def _finish(self) -> None:
        self._done = True
        self.on_done(self.party_number)

    def update(self, dt: float) -> None:
        if not self._done and self.sim and self.sim.enabled:
            self._finish()

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        tf = font(LAYOUT.i("party_title_size", 30))
        t = tf.render("Dungeon Party", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("party_title_y", 110))))
        sf = font(LAYOUT.i("party_sub_size", 17))
        sub = sf.render(f"Playing as {self.username}", True, _C["accent"])
        surface.blit(sub, sub.get_rect(center=(sw // 2, LAYOUT.i("party_sub_y", 168))))
        lf = font(LAYOUT.i("party_num_label_size", 20))
        lab = lf.render("Party number", True, _C["text_dim"])
        surface.blit(lab, lab.get_rect(center=(sw // 2, LAYOUT.i("party_num_y", 250) - 30)))
        nf = font(LAYOUT.i("party_num_value_size", 40))
        val = nf.render(str(self.party_number), True, _C["white"])
        surface.blit(val, val.get_rect(center=(sw // 2,
                     LAYOUT.i("party_num_y", 250) + LAYOUT.i("party_stepper_w", 64) // 2)))
        bf = font(LAYOUT.i("party_num_label_size", 20))
        for b in (self.minus_btn, self.plus_btn, self.create_btn, self.join_btn):
            b.draw(surface, bf)
```

- [x] **Step 3: Verify it constructs headlessly**

Run:
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "import pygame; pygame.init(); pygame.display.set_mode((414,896)); from src.ui.app import App; from src.ui.screens.party_screen import PartyScreen; a=App(); PartyScreen(a,'drpaj',lambda n: None, None).draw(a.screen); print('OK')"
```
Expected: `OK`. (If `App()` needs constructor args, mirror how other smoke checks build it -- check `TOOLS/` for an existing headless example.)

- [x] **Step 4: Commit**

```bash
git add src/ui/screens/party_screen.py
git commit -m "feat(ui): PartyScreen create/join with party-number stepper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: `PartyLobbyScreen`

**Files:**
- Create: `src/ui/screens/party_lobby_screen.py`

Polls `coordinator.refresh()` on the `party.poll_seconds` rhythm (the `_kick_poll` idiom from `LivePlayScreen`). Lists members + their gold. The leader's button action is supplied by the flow (`on_start` -- SIM seeds and starts; LIVE opens the fixture picker). When `coordinator.phase()` becomes `"shop"`, calls `on_advance()`.

- [x] **Step 1: Confirm the poll idiom + colors**

Re-read `LivePlayScreen._kick_poll`/`_poll` in `src/ui/screens/` (or wherever it lives) for the `asyncio.ensure_future` polling pattern, and confirm `_C` color keys (`surface`, `border`, `white`, `accent`, `text_dim`) exist in `config.colors`. Mirror them.

- [x] **Step 2: Write the screen**

Create `src/ui/screens/party_lobby_screen.py`:

```python
# src/ui/screens/party_lobby_screen.py
"""Party lobby: who has joined, and a wait for the leader to start. Polls the relay on the
party.poll_seconds rhythm. The leader sees a start button (action provided by the flow);
everyone advances when phase -> shop."""
import asyncio
from typing import TYPE_CHECKING, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, font
from src.ui.sim import SimMode
from src.sync.party_coordinator import PartyCoordinator
from src.utils.constants import CONFIG, LAYOUT

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_POLL = float(CONFIG["party"]["poll_seconds"])


class PartyLobbyScreen(Screen):
    def __init__(self, app: "App", coord: PartyCoordinator, on_start: Callable[[], None],
                 on_advance: Callable[[], None], start_label: str = "Start crawl",
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.coord = coord
        self.on_start = on_start
        self.on_advance = on_advance
        self.sim = sim
        self._polling = False
        self._elapsed = _POLL
        self._advanced = False
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.start_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("plobby_btn_h", 60) - 14, sw - 2 * m,
                        LAYOUT.i("plobby_btn_h", 60)), start_label)

    def handle(self, event: pygame.event.Event) -> None:
        if self.coord.is_leader and event.type == pygame.MOUSEBUTTONDOWN \
                and self.start_btn.hit(event.pos):
            self.on_start()

    def update(self, dt: float) -> None:
        if self._advanced:
            return
        self._elapsed += dt
        if not self._polling and self._elapsed >= _POLL:
            self._kick_poll()
        if self.sim and self.sim.enabled and self.coord.is_leader and self.coord.phase() == "lobby":
            self.on_start()
        if self.coord.phase() == "shop":
            self._advanced = True
            self.on_advance()

    def _kick_poll(self) -> None:
        self._polling = True
        self._elapsed = 0.0

        async def go() -> None:
            try:
                await self.coord.refresh()
            finally:
                self._polling = False
        asyncio.ensure_future(go())

    def draw(self, surface: pygame.Surface) -> None:
        sw = surface.get_width()
        m = LAYOUT.i("screen_margin", 20)
        tf = font(LAYOUT.i("plobby_title_size", 28))
        t = tf.render(f"Party {self.coord.party_id}", True, _C["white"])
        surface.blit(t, t.get_rect(center=(sw // 2, LAYOUT.i("plobby_title_y", 90))))
        sf = font(LAYOUT.i("plobby_sub_size", 16))
        sub = sf.render(f"you are slot {self.coord.slot}", True, _C["text_dim"])
        surface.blit(sub, sub.get_rect(center=(sw // 2, LAYOUT.i("plobby_sub_y", 140))))
        rf = font(LAYOUT.i("plobby_row_size", 20))
        top = LAYOUT.i("plobby_row_top", 200)
        step = LAYOUT.i("plobby_row_h", 56) + LAYOUT.i("plobby_row_gap", 10)
        for i, (name, gold) in enumerate(self.coord.view()["members"]):
            r = pygame.Rect(m, top + i * step, sw - 2 * m, LAYOUT.i("plobby_row_h", 56))
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            tag = "  (leader)" if i == 0 else ""
            surface.blit(rf.render(f"{i}. {name}{tag}", True, _C["white"]), (r.x + 14, r.y + 16))
        if self.coord.is_leader:
            self.start_btn.draw(surface, font(LAYOUT.i("plobby_row_size", 20)))
        else:
            hf = font(LAYOUT.i("plobby_hint_size", 16))
            h = hf.render("Waiting for the leader...", True, _C["accent"])
            surface.blit(h, h.get_rect(center=(sw // 2, surface.get_height() - 60)))
```

- [x] **Step 3: Verify it constructs headlessly**

Run:
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "
import asyncio, pygame; pygame.init(); pygame.display.set_mode((414,896))
from tests.test_party_coordinator import FakeRelay, _pool, _actuals
from src.sync.party_coordinator import PartyCoordinator
from src.ui.app import App
from src.ui.screens.party_lobby_screen import PartyLobbyScreen
r=FakeRelay(); c=PartyCoordinator(r,0,'drpaj',_pool(),_actuals); asyncio.run(c.join())
a=App(); PartyLobbyScreen(a,c,lambda:None,lambda:None,'Start',None).draw(a.screen); print('OK')"
```
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add src/ui/screens/party_lobby_screen.py
git commit -m "feat(ui): PartyLobbyScreen with relay polling and leader start

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: `PartyPlayScreen`

**Files:**
- Create: `src/ui/screens/party_play_screen.py`

Each member edits their **own** five dials (same controls as `DungeonPlayScreen`'s predict phase), then Submit -> `coordinator.submit_pick`. Then it polls; the leader's poll additionally tries to resolve (and, in LIVE, calls a flow `on_poll`). When `coordinator.resolved_through() >= window`, it renders the pushed dungeon `view()` (depth meter, window-color cells, crawl log) + the live scoreline, and shows Continue -> `on_continue()`. Advance is driven by the flow (manual Continue in SIM; the flow's clock in LIVE may call `force_resolve()`).

- [x] **Step 1: Confirm widget + layout names**

From `dungeon_play_screen.py` (already read): reuses `Button`, `LogList`, `draw_depth_meter`, `font`, `gate_step`, the `dp_*` layout keys, and the `_STATS` menu. Confirm those imports/keys still resolve. Mirror the `_stat_rect`/`_tap_stat` geometry exactly.

- [x] **Step 2: Write the screen**

Create `src/ui/screens/party_play_screen.py`:

```python
# src/ui/screens/party_play_screen.py
"""One window of the cooperative crawl on this member's device.

Phase 'edit': five dials + Submit -> coordinator.submit_pick. Phase 'wait': poll the relay;
the leader also tries to resolve (require_all unless the flow forces a boundary) and runs an
optional on_poll hook (LIVE feed fetch+share). Phase 'resolved': render the pushed depth/colors/
log + live scoreline + Continue. Resolution authority lives on the leader, never here."""
import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

import pygame

from src.ui.screens.base import Screen
from src.ui.widgets import Button, LogList, draw_depth_meter, font
from src.ui.sim import SimMode
from src.sync.party_coordinator import PartyCoordinator
from src.game.dungeon import gate_step
from src.utils.constants import CONFIG, LAYOUT, load_data

if TYPE_CHECKING:
    from src.ui.app import App

_C = CONFIG["colors"]
_STATS = load_data(CONFIG["assets"]["stats_menu_file"])["stats"]
_POLL = float(CONFIG["party"]["poll_seconds"])


class PartyPlayScreen(Screen):
    def __init__(self, app: "App", coord: PartyCoordinator, window: int, label: str,
                 on_continue: Callable[[], None], require_all: bool = True,
                 on_poll: Optional[Callable[[], Awaitable[None]]] = None,
                 sim: Optional[SimMode] = None) -> None:
        super().__init__(app)
        self.coord = coord
        self.window = window
        self.label = label
        self.on_continue = on_continue
        self.require_all = require_all
        self.on_poll = on_poll
        self.sim = sim
        self.phase = "edit"
        self.lines = {s["code"]: s["default_line"] for s in _STATS}
        self._polling = False
        self._elapsed = _POLL
        self._logged = 0
        sw, sh = app.screen.get_size()
        m = LAYOUT.i("screen_margin", 20)
        self.log = LogList(pygame.Rect(m, LAYOUT.i("dp_content_top", 92),
                                       sw - 2 * m, LAYOUT.i("dp_log_h", 150)))
        self.action_btn = Button(
            pygame.Rect(m, sh - LAYOUT.i("dp_btn_h", 56) - 12, sw - 2 * m,
                        LAYOUT.i("dp_btn_h", 56)), "Submit picks")

    def _stat_step(self) -> int:
        return LAYOUT.i("dp_stat_row_h", 48) + LAYOUT.i("dp_stat_gap", 6)

    def _stat_rect(self, i: int) -> pygame.Rect:
        m = LAYOUT.i("screen_margin", 20)
        top = LAYOUT.i("dp_content_top", 92)
        w = self.app.screen.get_width() - 2 * m
        return pygame.Rect(m, top + i * self._stat_step(), w, LAYOUT.i("dp_stat_row_h", 48))

    def handle(self, event: pygame.event.Event) -> None:
        if self.phase == "edit":
            if self.sim and self.sim.is_key(event, pygame.K_f):
                self._submit()
                return
            if event.type != pygame.MOUSEBUTTONDOWN:
                return
            if self.action_btn.hit(event.pos):
                self._submit()
                return
            for i, s in enumerate(_STATS):
                r = self._stat_rect(i)
                if r.collidepoint(event.pos):
                    self._tap_stat(s["code"], event.pos[0], r)
                    return
        elif self.phase == "resolved":
            self.log.handle(event)
            if event.type == pygame.MOUSEBUTTONDOWN and self.action_btn.hit(event.pos):
                self.on_continue()
            elif self.sim and self.sim.is_key(event, pygame.K_s):
                self.on_continue()

    def _tap_stat(self, code: str, x: int, r: pygame.Rect) -> None:
        if x > r.right - 56:
            self.lines[code] += 1
        elif x > r.right - 112:
            self.lines[code] = max(0, self.lines[code] - 1)

    def _submit(self) -> None:
        asyncio.ensure_future(self.coord.submit_pick(self.window, dict(self.lines)))
        self.phase = "wait"

    def force_resolve(self) -> None:
        """Flow hook (LIVE): the match clock crossed this window's boundary. If still editing,
        auto-submit the current dials; the leader will resolve with require_all=False."""
        if self.phase == "edit":
            self._submit()
        self.require_all = False

    def update(self, dt: float) -> None:
        if self.phase == "edit":
            return
        self._elapsed += dt
        if not self._polling and self._elapsed >= _POLL:
            self._kick_poll()
        if self.phase == "wait" and self.coord.resolved_through() >= self.window:
            self._enter_resolved()

    def _kick_poll(self) -> None:
        self._polling = True
        self._elapsed = 0.0

        async def go() -> None:
            try:
                await self.coord.refresh()
                if self.on_poll is not None:
                    await self.on_poll()
                if self.coord.is_leader:
                    await self.coord.leader_try_resolve(self.window, self.require_all)
            finally:
                self._polling = False
        asyncio.ensure_future(go())

    def _enter_resolved(self) -> None:
        self.phase = "resolved"
        for line in self.coord.view()["log"][self._logged:]:
            self.log.add(line)
        self._logged = len(self.coord.view()["log"])
        self.action_btn.label = "Continue"

    def draw(self, surface: pygame.Surface) -> None:
        m = LAYOUT.i("screen_margin", 20)
        v = self.coord.view()
        hf = font(LAYOUT.i("dp_header_size", 18))
        surface.blit(hf.render(self.label, True, _C["accent"]), (m, LAYOUT.i("dp_header_y", 14)))
        scf = font(LAYOUT.i("pplay_score_size", 16))
        mt = v.get("match", {})
        score = (f"{mt.get('home','')} {mt.get('home_goals',0)}-{mt.get('away_goals',0)} "
                 f"{mt.get('away','')}  ({mt.get('minute',0)}')") if mt.get("home") else ""
        surface.blit(scf.render(score, True, _C["text_dim"]), (m, LAYOUT.i("pplay_score_y", 38)))
        stf = font(LAYOUT.i("dp_status_size", 16))
        status = f"Power {v['power']}   Wounds {v['wounds']}   My gold {self.coord.my_treasury()}"
        surface.blit(stf.render(status, True, _C["white"]), (m, LAYOUT.i("dp_status_y", 60)))
        if self.phase == "edit":
            self._draw_dials(surface)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))
        elif self.phase == "wait":
            wf = font(LAYOUT.i("pplay_wait_size", 20))
            msg = "Resolving..." if self.coord.is_leader else "Waiting for the party..."
            w = wf.render(msg, True, _C["accent"])
            surface.blit(w, w.get_rect(center=(surface.get_width() // 2,
                                               LAYOUT.i("pplay_wait_y", 420))))
        else:
            self._draw_resolved(surface, v)
            self.action_btn.draw(surface, font(LAYOUT.i("dp_stat_size", 19)))

    def _draw_dials(self, surface: pygame.Surface) -> None:
        sf = font(LAYOUT.i("dp_stat_size", 19))
        for i, s in enumerate(_STATS):
            r = self._stat_rect(i)
            pygame.draw.rect(surface, _C["surface"], r, border_radius=8)
            pygame.draw.rect(surface, _C["border"], r, width=2, border_radius=8)
            surface.blit(sf.render(f"{s['label']}: {self.lines[s['code']]}", True, _C["white"]),
                         (r.x + 12, r.y + 12))
            surface.blit(sf.render("-", True, _C["white"]), (r.right - 104, r.y + 10))
            surface.blit(sf.render("+", True, _C["white"]), (r.right - 44, r.y + 10))

    def _draw_resolved(self, surface: pygame.Surface, v: dict) -> None:
        self.log.draw(surface)
        m = LAYOUT.i("screen_margin", 20)
        cells_y = self.log.rect.bottom + LAYOUT.i("dp_section_gap", 24)
        h, gap = LAYOUT.i("dp_cells_h", 28), LAYOUT.i("dp_cell_gap", 6)
        for i, key in enumerate(v["window_colors"]):
            cell = pygame.Rect(m + i * (h + gap), cells_y, h, h)
            pygame.draw.rect(surface, _C.get(key, _C["orange"]), cell, border_radius=6)
        meter_y = cells_y + h + LAYOUT.i("dp_section_gap", 24)
        color = v["window_colors"][-1] if v["window_colors"] else "orange"
        draw_depth_meter(surface, pygame.Rect(m, meter_y, surface.get_width() - 2 * m, 0),
                         v["depth"], v["total"], gate_step(self.coord.half()), color)
```

- [x] **Step 3: Verify it constructs and renders all phases headlessly**

Run:
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "
import asyncio, pygame; pygame.init(); pygame.display.set_mode((414,896))
from tests.test_party_coordinator import FakeRelay, _pool, _actuals
from src.sync.party_coordinator import PartyCoordinator
from src.ui.app import App
from src.ui.screens.party_play_screen import PartyPlayScreen
r=FakeRelay(); c=PartyCoordinator(r,0,'drpaj',_pool(),_actuals); asyncio.run(c.join())
asyncio.run(c.leader_start()); asyncio.run(c.refresh())
asyncio.run(c.submit_loadout([], c.shop_budget()))
asyncio.run(c.leader_try_reconcile_shop()); asyncio.run(c.refresh())
a=App(); s=PartyPlayScreen(a,c,1,'H1 W1',lambda:None,True,None,None)
s.draw(a.screen)                       # edit
s.phase='wait'; s.draw(a.screen)       # wait
asyncio.run(c.submit_pick(1,{'goal':1,'shot':3,'corner':3,'card':1,'foul':4}))
asyncio.run(c.refresh()); asyncio.run(c.leader_try_resolve(1)); asyncio.run(c.refresh())
s._enter_resolved(); s.draw(a.screen)  # resolved
print('OK')"
```
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add src/ui/screens/party_play_screen.py
git commit -m "feat(ui): PartyPlayScreen per-member dials + poll + resolved render + scoreline

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: `DungeonPartyFlow` (SIM) + launcher + `--party`

**Files:**
- Modify: `src/ui/flow.py`
- Modify: `src/main.py`

This task wires the **SIM** party (recorded feed, manual advance) end-to-end -- the fully testable path. The LIVE wiring is Task 14.

- [x] **Step 1: Read the integration points first**

Read `src/ui/flow.py` in full. Confirm verbatim: `start_dungeon_sim`, `DungeonSimFlow`, `start_app`, `start_launcher`, `_pool_from_feed`, `_HALF_MIN`, `_WINDOW_MIN`, `_WINDOWS_PER_HALF`, `_HALF_LABEL`, `_SECOND_HALF_LABEL`, `_FULLTIME_LABEL`, `_RNG_SEED`, `_LAUNCHER`, `_STATS_MENU`, `ReplayFeed`, `ShopScreen`, `DungeonFinalScreen`, `SplashScreen`, `CrawlSession`, `SimMode`, `CONFIG`, and the test-sim path key (e.g. `_LAUNCHER["test_sim"]`). Confirm `app.set_screen`, `app.global_handler`, `app.overlay`, the `RelayClient` import path and constructor (`RelayClient(base_url, api_path=...)` or similar), and `from src.game.normalize_soccer import actuals_from_raw`. Adapt names if any differ; do not invent.

- [x] **Step 2: Add imports and the flow class**

Add to the import block (and `import random` / `import asyncio` if not present):

```python
from src.ui.screens.party_screen import PartyScreen
from src.ui.screens.party_lobby_screen import PartyLobbyScreen
from src.ui.screens.party_play_screen import PartyPlayScreen
from src.sync.relay_client import RelayClient
from src.sync.party_coordinator import PartyCoordinator
```

After `DungeonSimFlow`, add:

```python
class DungeonPartyFlow:
    """Online cooperative crawl. The leader holds the authoritative CrawlSession inside the
    PartyCoordinator; followers poll and render. SIM mode runs over a recorded feed with manual
    window advance (deterministic, testable). LIVE mode (attach_live + start_dungeon_party_live)
    runs over the real feed on the match clock; that wiring reuses this flow's steps."""

    def __init__(self, app: "App", feed, pool, coord: PartyCoordinator, sim: SimMode) -> None:
        self.app = app
        self.feed = feed
        self.pool = pool
        self.coord = coord
        self.sim = sim
        self.app.global_handler = sim.handle_global
        self.app.overlay = sim.draw_overlay
        self.window = 1
        self._local_shop = None
        self.live = False

    def start(self) -> None:
        self.app.set_screen(SplashScreen(self.app, self._to_lobby, self.sim))

    def _to_lobby(self) -> None:
        self.app.set_screen(PartyLobbyScreen(
            self.app, self.coord, on_start=self._leader_start, on_advance=self._to_shop,
            start_label="Start crawl", sim=self.sim))

    def _leader_start(self) -> None:
        asyncio.ensure_future(self.coord.leader_start())

    def _to_shop(self) -> None:
        # Each member buys against a LOCAL party_size=1 session funded by their own pot; only
        # their own loadout is submitted. The catalog is built from the shared pool.
        budget = max(1, self.coord.shop_budget())
        local = CrawlSession(party_size=1, pool=self.pool, rng=random.Random(_RNG_SEED),
                             half=self.coord.half(), treasury=budget)
        self._local_shop = local
        self.app.set_screen(ShopScreen(self.app, local, self._after_shop, self.sim, member=0))

    def _after_shop(self) -> None:
        item_ids = [it.item_id for it in self._local_shop.loadouts[0].items]
        asyncio.ensure_future(self._submit_loadout_then_wait(item_ids,
                                                             self._local_shop.treasury))

    async def _submit_loadout_then_wait(self, item_ids: list, treasury: int) -> None:
        await self.coord.submit_loadout(item_ids, treasury)
        await self.coord.refresh()
        if self.coord.is_leader:
            await self.coord.leader_try_reconcile_shop()
        self.window = 1
        self._play_window()

    def _label(self) -> str:
        half_label = _HALF_LABEL if self.coord.half() == 1 else _SECOND_HALF_LABEL
        return f"{half_label} -- Window {self.window}/{_WINDOWS_PER_HALF}"

    def _play_window(self) -> None:
        self.app.set_screen(PartyPlayScreen(self.app, self.coord, self.window, self._label(),
                                            self._on_continue, require_all=True, sim=self.sim))

    def actuals_for(self, window: int) -> dict:
        start = (self.coord.half() - 1) * _HALF_MIN + (window - 1) * _WINDOW_MIN
        end = start + _WINDOW_MIN
        a = self.feed.snapshot_at(start)
        b = self.feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)

    def _on_continue(self) -> None:
        if self.window < _WINDOWS_PER_HALF:
            self.window += 1
            self._play_window()
        elif self.coord.half() == 1:
            asyncio.ensure_future(self._advance_then_shop())
        else:
            asyncio.ensure_future(self._advance_then_finish())

    async def _advance_then_shop(self) -> None:
        if self.coord.is_leader:
            await self.coord.leader_advance_half()
        else:
            await self.coord.refresh()
        self._to_shop()

    async def _advance_then_finish(self) -> None:
        if self.coord.is_leader:
            await self.coord.leader_advance_half()
        else:
            await self.coord.refresh()
        v = self.coord.view()
        self.app.set_screen(DungeonFinalScreen(self.app, v["percent"], v["depth"], v["total"],
                                               on_continue=None, title=_FULLTIME_LABEL))
```

(If `DungeonFinalScreen`'s constructor signature differs, match `DungeonSimFlow`'s `_to_final` call exactly.)

- [x] **Step 3: Add the SIM entry point + launcher option**

After `start_dungeon_sim(...)`, add (adapt the `RelayClient` constructor to the real signature found in Step 1):

```python
def start_dungeon_party(app: "App", username: str, sim_rel_path: str,
                        sim_mode: bool = True) -> None:
    """SIM cooperative party: a recorded match drives deterministic per-window actuals on
    every client; windows advance manually. The username (from UsernameScreen) is the party
    credential. LIVE entry is start_dungeon_party_live (Task 14)."""
    feed = ReplayFeed.from_file(sim_rel_path)
    pool = _pool_from_feed(feed)
    sim = SimMode(sim_mode)
    relay = RelayClient(CONFIG["relay"]["base_url"], api_path=CONFIG["relay"]["api_path"])

    def picked(party_number: int) -> None:
        coord = PartyCoordinator(relay=relay, party_id=party_number, username=username,
                                 pool=pool, actuals_fn=lambda w: flow.actuals_for(w))
        flow = DungeonPartyFlow(app, feed, pool, coord, sim)

        async def go() -> None:
            await coord.join()
            flow.start()
        asyncio.ensure_future(go())

    app.global_handler = sim.handle_global
    app.overlay = sim.draw_overlay
    app.set_screen(PartyScreen(app, username, picked, sim))
```

In `start_launcher(...)`, after `go_dungeon`, add and register:

```python
    def go_party() -> None:
        start_dungeon_party(app, username, _LAUNCHER["test_sim"], sim_mode=sim_mode)
```
```python
        (_LAUNCHER["party_label"], go_party),
```
(Match the exact structure the launcher uses for its option list/labels.)

- [x] **Step 4: Add the `--party` desktop argument**

In `src/main.py`, mirroring the `--dungeon` branch, add:

```python
    elif "--party" in sys.argv:
        flow.start_dungeon_party(app, "drpaj", CONFIG["launcher"]["test_sim"],
                                 sim_mode="--sim" in sys.argv)
```

(Match the existing branch's import/call style exactly; use the real test-sim config key.)

- [x] **Step 5: Verify the flow lands on the party screen headlessly**

Run:
```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "
import pygame; pygame.init(); pygame.display.set_mode((414,896))
from src.ui.app import App
from src.ui import flow
from src.utils.constants import CONFIG
from src.ui.screens.party_screen import PartyScreen
a=App(); flow.start_dungeon_party(a,'drpaj',CONFIG['launcher']['test_sim'], sim_mode=False)
assert isinstance(a.current, PartyScreen), type(a.current)
print('OK')"
```
Expected: `OK` (use the real `app.current`/`app.screen` attribute that holds the active screen).

- [x] **Step 6: Full suite + launch check**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all pass.
(Manual, by the user: `.venv/Scripts/python src/main.py --party --sim`.)

- [x] **Step 7: Commit**

```bash
git add src/ui/flow.py src/main.py
git commit -m "feat(flow): DungeonPartyFlow SIM party + launcher option + --party entry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: LIVE party wiring (real feed + match clock)

**Files:**
- Modify: `src/ui/flow.py`
- Modify: `config/game_config.json` (already has `launcher.party_live_label` from Task 1)

This grafts the LIVE timing onto `DungeonPartyFlow`, reusing the existing live stack. It cannot be fully headless-verified (needs a real match or a hand-fed `LiveFeed` over time); the construct-smoke confirms it builds and the leader's feed-share path runs.

- [x] **Step 1: Read the live stack**

Read in `src/ui/flow.py` the entire `start_live` / `start_live_select` functions and the `LiveFlow` class, including `_window_actuals_for`, `launch_half`, and how it builds `HalfClock`/`MatchClock`, `FeedClient`, `LiveResolveScreen`, `LiveWaitScreen`, `FixtureSelectScreen`. Read these modules' public APIs: `src/game/live_feed.py` (`LiveFeed.record/snapshot_at/current_minute/home_team/away_team/home_goals/away_goals/status_short/has_lineups/lineups/kickoff_iso/last_known_minute`), `src/game/half_clock.py` (`HalfClock`), `src/game/match_clock.py` (`MatchClock.editing_window`), `src/sync/feed_client.py` (`FeedClient`). Note config keys `relay.feed_path`, `relay.live_fixtures_path`, `client.lead_username`, `game.window_seconds`, `game.half_minutes`.

- [x] **Step 2: Add the live-feed-share + live-actuals methods to `DungeonPartyFlow`**

```python
    def attach_live(self, feed_client, live_feed, fixture_id: int, clock) -> None:
        """LIVE mode: the leader fetches the feed and shares match/pool; the match clock drives
        window boundaries. clock is a HalfClock."""
        self.feed_client = feed_client
        self.live_feed = live_feed
        self.fixture_id = fixture_id
        self.clock = clock
        self.feed = live_feed
        self.live = True

    async def leader_poll_feed(self) -> None:
        """Leader only: fetch one relay snapshot, record it, and share match summary (+ pool
        once lineups arrive) into the blob. Guarded -- a network failure must not crash play."""
        if not self.live or not self.coord.is_leader:
            return
        try:
            snap = await self.feed_client.get_feed(self.fixture_id)
            self.live_feed.record(snap)
        except Exception:
            return
        match = {"home": self.live_feed.home_team(), "away": self.live_feed.away_team(),
                 "home_goals": self.live_feed.home_goals(),
                 "away_goals": self.live_feed.away_goals(),
                 "minute": self.live_feed.current_minute(),
                 "status": self.live_feed.status_short()}
        pool_rows = None
        if not self.coord.party.pool and self.live_feed.has_lineups():
            pool_rows = self.live_feed.lineups()
        await self.coord.leader_share_match(match, pool_rows=pool_rows,
                                            fixture_id=self.fixture_id,
                                            kickoff_iso=self.live_feed.kickoff_iso() or "")

    def live_actuals_for(self, window: int) -> dict:
        """Actuals from the live feed for one window (extra-time end discovered via
        last_known_minute, mirroring LiveFlow._window_actuals_for)."""
        start = self.clock.window_start(window)
        end = (self.live_feed.last_known_minute() if self.clock.is_extra_time(window)
               else self.clock.window_end(window))
        a = self.live_feed.snapshot_at(start)
        b = self.live_feed.snapshot_at(end)
        from src.game.normalize_soccer import actuals_from_raw
        raw = {k: b.delta(a, k) for k in (set(a.stats) | set(b.stats))}
        return actuals_from_raw(raw, _STATS_MENU)
```

In LIVE mode the `PartyPlayScreen` is built with `require_all=False`, `on_poll=self.leader_poll_feed`, and the flow drives `force_resolve()` when the `MatchClock.editing_window(now)` advances past the current window. Add a `_play_window_live()` that constructs the screen with those args and starts a per-frame clock check (reuse `MatchClock` the way `LiveFlow` does -- store it on the flow and compare `editing_window(now)` to `self.window` inside the screen's poll via a small flow callback, or set `screen.force_resolve()` from the flow's own `update` hook if the app exposes one). Keep `_on_continue` as the post-resolve advance.

- [x] **Step 3: Add `start_dungeon_party_live`**

Model on `start_live` / `start_live_select`. Reuse `FixtureSelectScreen` -> `LiveResolveScreen` -> `LiveWaitScreen` (wait for lineups) to obtain the real `fixture_id` + lineups, build `pool = _pool_from_feed(live_feed)`, construct `PartyCoordinator(actuals_fn=flow.live_actuals_for)`, `await coord.join()`, then run `DungeonPartyFlow` with `attach_live(...)`. The leader uses `FeedClient(..., is_lead=True)`; followers `is_lead=False`. `is_lead` is `username.lower() == CONFIG["client"]["lead_username"].lower()`, matching `start_app`. The lobby's leader button is labelled "Pick match" and its `on_start` opens the picker (leader only); followers' lobby just polls until the leader shares the fixture + pool, then advances. Build the full function following the exact constructor signatures discovered in Step 1; guard every network call so a follower with no feed still renders from the blob.

- [x] **Step 4: Add the LIVE launcher option**

In `start_launcher`, add a `go_party_live` option using `_LAUNCHER["party_live_label"]` that calls `start_dungeon_party_live(app, username, is_lead=is_lead, sim_mode=sim_mode)`. Keep the SIM `go_party` option from Task 13.

- [x] **Step 5: Verify the share path builds + runs headlessly**

Run a construct smoke that builds a leader `DungeonPartyFlow`, calls `attach_live` with a `LiveFeed` and a `HalfClock`, runs `await flow.leader_poll_feed()` against a fake `FeedClient` returning one recorded snapshot, and asserts the blob's `match` populated:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/Scripts/python -c "
import asyncio, pygame; pygame.init(); pygame.display.set_mode((414,896))
from tests.test_party_coordinator import FakeRelay, _pool, _actuals
from src.sync.party_coordinator import PartyCoordinator
from src.game.live_feed import LiveFeed
from src.game.half_clock import HalfClock
from src.ui.app import App
from src.ui import flow
class FakeFC:
    async def get_feed(self, fid):
        return {SNAPSHOT_SHAPE_FROM_STEP1}
r=FakeRelay(); pool=_pool()
coord=PartyCoordinator(r,0,'drpaj',pool,_actuals); asyncio.run(coord.join())
asyncio.run(coord.leader_start()); asyncio.run(coord.refresh())
a=App(); f=flow.DungeonPartyFlow(a, None, pool, coord, flow.SimMode(False))
f.attach_live(FakeFC(), LiveFeed(), 999, HalfClock(45,15,start_minute=0))
asyncio.run(f.leader_poll_feed())
assert coord.party.match['home'], coord.party.match
print('OK')"
```
Replace `{SNAPSHOT_SHAPE_FROM_STEP1}` with the exact dict `LiveFeed.record` expects (read its signature in Step 1). Expected: `OK`.

- [x] **Step 6: Full suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all pass (no pure tests touched here).

- [x] **Step 7: Commit**

```bash
git add src/ui/flow.py config/game_config.json
git commit -m "feat(flow): LIVE party wiring -- leader-fetched feed shared via relay, clock-driven windows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Smoke script + log

**Files:**
- Create: `TOOLS/smoke_party.py`
- Modify: `log.md`

Headless end-to-end: an in-memory relay drives a leader + 2 followers through a full two-half SIM crawl (per-player economy, gold split, leader-authoritative resolution), then draws the three screens.

- [x] **Step 1: Write the smoke script**

Create `TOOLS/smoke_party.py`:

```python
# TOOLS/smoke_party.py
"""Headless party smoke: in-memory relay, 3 coordinators (leader + 2 followers), a full
2-half crawl with the per-player economy, then draw the three party screens. ASCII-only.
Run from repo root:  .venv/Scripts/python TOOLS/smoke_party.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from tests.test_party_coordinator import FakeRelay, _pool, _actuals
from src.sync.party_coordinator import PartyCoordinator
from src.utils.constants import CONFIG

_WPH = int(CONFIG["game"]["windows_per_half"])
_PER = int(CONFIG["party"]["per_player_treasury"])


async def _drive() -> int:
    relay, pool = FakeRelay(), _pool()
    lead = PartyCoordinator(relay, 0, "drpaj", pool, _actuals)
    a = PartyCoordinator(relay, 0, "alice", pool, _actuals)
    b = PartyCoordinator(relay, 0, "bob", pool, _actuals)
    members = (lead, a, b)
    for c in members:
        await c.join()
    assert lead.is_leader and not a.is_leader, "leader assignment FAIL"

    for half in (1, 2):
        if half == 1:
            await lead.leader_start()
        for c in members:
            await c.refresh()
            await c.submit_loadout([], c.shop_budget())
        await lead.leader_try_reconcile_shop()
        for c in members:
            await c.refresh()
        assert lead.phase() == "play", f"half {half} not in play: {lead.phase()}"
        for w in range(1, _WPH + 1):
            for c in members:
                await c.submit_pick(w, {"goal": 1, "shot": 3, "corner": 3,
                                        "card": 1, "foul": 4})
            await lead.refresh()
            await lead.leader_try_resolve(w)
            for c in members:
                await c.refresh()
            assert lead.resolved_through() == w, f"window {w} not resolved"
            assert a.view()["depth"] == lead.view()["depth"], "follower depth mismatch FAIL"
        await lead.leader_advance_half()
        for c in members:
            await c.refresh()

    assert lead.phase() == "done", f"did not finish: {lead.phase()}"
    pct = lead.view()["percent"]
    print(f"OK  crawl complete  depth={lead.view()['depth']}  percent={pct}%  "
          f"gold drpaj={lead.my_treasury()} alice={a.my_treasury()} bob={b.my_treasury()}")
    return pct


def _draw_screens() -> None:
    import pygame
    pygame.init()
    pygame.display.set_mode((CONFIG["display"]["width"], CONFIG["display"]["height"]))
    from src.ui.app import App
    from src.ui.screens.party_screen import PartyScreen
    from src.ui.screens.party_lobby_screen import PartyLobbyScreen
    from src.ui.screens.party_play_screen import PartyPlayScreen
    relay, pool = FakeRelay(), _pool()
    coord = PartyCoordinator(relay, 0, "drpaj", pool, _actuals)
    asyncio.run(coord.join())
    app = App()
    PartyScreen(app, "drpaj", lambda n: None, None).draw(app.screen)
    PartyLobbyScreen(app, coord, lambda: None, lambda: None, "Start", None).draw(app.screen)
    PartyPlayScreen(app, coord, 1, "H1 W1", lambda: None, True, None, None).draw(app.screen)
    print("OK  drew party / lobby / play screens")


def main() -> None:
    pct = asyncio.run(_drive())
    _draw_screens()
    if pct <= 0:
        print("FAIL  crawl made no progress")
        sys.exit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
```

(Adapt `CONFIG["display"]["width"]/["height"]` to the real display config keys; check `config/game_config.json`. `PartyPlayScreen(...)` arg order must match Task 12's final signature -- update if `on_poll` precedes `sim`.)

- [x] **Step 2: Run the smoke**

Run: `.venv/Scripts/python TOOLS/smoke_party.py`
Expected: ends with `SMOKE OK`. Fix the implicated module if it fails.

- [x] **Step 3: Full suite once more**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: all pass.

- [x] **Step 4: Append the log line**

Append to `log.md` (ASCII only):

```
2026-06-22 | Plan 2 complete: live co-op dungeon party (per-player economy, leader-authoritative resolution, party model+relay+coordinator, SIM+LIVE flows, 3 screens, smoke) | src/game/party.py, src/game/dungeon.py, src/game/crawl.py, src/sync/relay_client.py, src/sync/party_coordinator.py, php/soccer_api.php, src/ui/screens/party_screen.py, src/ui/screens/party_lobby_screen.py, src/ui/screens/party_play_screen.py, src/ui/flow.py, src/main.py, config/*.json, TOOLS/smoke_party.py
```

- [x] **Step 5: Commit**

```bash
git add TOOLS/smoke_party.py log.md
git commit -m "test(party): headless 3-member two-half SIM smoke + log

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage (the locked decisions):**
- Live feed leader-fetched + shared: Task 8 (blob `match`/`pool`/`fixture_id`), Task 9 (`leader_share_match`), Task 14 (`leader_poll_feed` via `FeedClient(is_lead)`; followers render the blob, never call the API). OK.
- Two timing modes: SIM (Task 13, manual `_on_continue`); LIVE (Task 14, `MatchClock` boundary -> `force_resolve` -> `leader_try_resolve(require_all=False)`). OK.
- Single half core + gold spillover into harder H2: Task 9 (`leader_advance_half` keeps carried `treasury`, `begin_second_half` carries Power + harder gates), Task 13 (`_advance_then_shop`). OK.
- Per-player economy + independent loadouts + duplicates + equal gold split: Task 2 (`Member.treasury`), Task 6 (`set_loadout`, no charge, duplicates allowed across members), Task 4 (`split_gold`), Task 9 (seed per-player pot, split gold into each pot), Task 13 (local party_size=1 shop funded by own pot). OK.
- Rejoin-by-username: Task 3 + Task 8 (`party_join` create-or-join, cap 3). OK.
- Existing room endpoints + client tests intact: Task 8 (additive), Task 7 (existing tests preserved). OK.

**2. Placeholder scan:** Pure/relay/coordinator/screens tasks (1-13, 15) contain complete code. Task 14 (LIVE wiring) intentionally gives full code for the testable share/actuals helpers and detailed structure + exact reuse targets for `start_dungeon_party_live` and the clock-boundary `force_resolve`, because that body depends on existing constructor signatures the implementer reads in Step 1 -- this is flagged, not a silent gap. The one cross-file assumption (`tests/test_crawl.py` pool helper; `score.py` helper names; display config keys) is called out in the relevant tasks with instructions to use the real names.

**3. Type consistency:**
- `Party.join_or_restore -> (Optional[int], bool)` consumed identically by `FakeRelay`, PHP, and the coordinator.
- `fighter_lines_from_picks(party, window) -> list[dict]` feeds `CrawlSession.resolve_window(fighter_lines, actuals, label)` (Plan 1b arg order, matching `DungeonSimFlow._on_descend`).
- Coordinator surface used by screens (`refresh/phase/half/resolved_through/view/my_treasury/shop_budget/is_leader/slot/party_id/submit_pick/submit_loadout/leader_start/leader_try_reconcile_shop/leader_try_resolve/leader_advance_half/leader_share_match/last_gold`) all defined in Task 9 and used identically in Tasks 11-14.
- `view()` keys (`depth/total/power/wounds/log/window_colors/members/match/percent`) defined in Task 9, consumed in Tasks 11-12, 15.
- Relay client signatures (Task 7) match `FakeRelay` (Task 9) and PHP actions (Task 8): `party_loadout(party, username, item_ids, treasury)` carries treasury in all three.
- `set_loadout(member, item_ids) -> list[str]` (Task 6) called by `leader_try_reconcile_shop` (Task 9) per member slot.
- `PartyPlayScreen(...)` signature (Task 12: `..., require_all, on_poll, sim`) used consistently in Tasks 13 (`require_all=True, sim=`), 14 (`on_poll=`), and 15 (positional `True, None, None`). Note for implementer: keep keyword args at call sites to avoid positional drift.

**4. Ordering:** pure model (2-6) -> relay (7-8) -> coordinator (9) -> SIM UI/flow (10-13) -> LIVE wiring (14) -> smoke (15). Each task's tests depend only on earlier tasks. Tasks share files (`party.py` across 2-4; `flow.py`/`config` across 13-14) so they are **sequential** -- do not parallelize implementers.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-22-party-relay-plan-2.md`.
