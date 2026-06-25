# PJAB's Fanbidextrous Game — Claude Code Reference

## CRITICAL: Read these files first, every session
1. Read `DESIGN.md`       -- understand what game we are building
2. Read `log.md`          -- see what was last done and where to pick up
3. Read `config/game_config.json` -- understand all settings before touching code

## Session start protocol
After reading the three files above:
- State what was last completed (from log.md)
- State what you will work on next
- Ask one clarifying question if anything in DESIGN.md is ambiguous
- Then start -- do not ask for permission to begin

---

## Architecture rules (NEVER break these)

### The golden rule: keep game logic and rendering separate
- `src/game/`   contains ZERO pygame imports -- pure Python only, always testable
- `src/ui/`     contains ALL pygame rendering -- never import from src/game/ in reverse
- `config/`     contains ALL constants -- no magic numbers anywhere in code
- `tests/`      tests src/game/ only -- no pygame in tests

### Code standards
- Type hints on every function signature
- No global variables -- pass state through constructors and method arguments
- Comments explain WHY, not WHAT -- good names explain what
- One class or one logical group of functions per file
- All JSON keys in snake_case

### Config rule
Every number that could ever change lives in `config/game_config.json`.
Load it once at startup via `src/utils/constants.py`.
Never hardcode a color, a screen size, a speed, or a score value.

---

## Workflow -- one increment at a time

Do not write the whole game in one session. Each increment:
1. Pick ONE module to build or extend
2. Write it
3. Run `python -m pytest tests/` -- fix anything that breaks
4. Run `python src/main.py` -- verify the game still launches
5. Append one line to `log.md`
6. Stop and report what was done

If tests fail, fix them before moving on. Never leave tests broken.

---

## After every change
- Append to `log.md` in the format:  `YYYY-MM-DD | [what changed] | [files touched]`
- Run tests
- Confirm the game launches

---

## Directory layout

```
your-game/
+-- CLAUDE.md               <- you are here
+-- DESIGN.md               <- game design spec (read this first)
+-- README.md               <- play instructions
+-- requirements.txt        <- pip dependencies
+-- log.md                  <- running changelog
+-- .gitignore              <- what git should not track
+-- main.py                 <- web entry point (pygbag reads this)
+-- pygbag.ini              <- web build title/package/dimensions
+-- src/
|   +-- main.py             <- desktop entry point (keep this small)
|   +-- game/               <- pure Python, zero pygame
|   |   +-- game_state.py   <- all game state lives here
|   |   +-- rules.py        <- win conditions, scoring, turn logic
|   |   +-- entities.py     <- your game's objects: cards, units, tiles, etc.
|   +-- ui/
|   |   +-- game_window.py  <- pygame event loop and state machine (async, for pygbag)
|   |   +-- components.py   <- buttons, labels, panels
|   +-- utils/
|       +-- constants.py    <- loads config/game_config.json
|       +-- asset_loader.py <- images, sounds, fonts
+-- config/
|   +-- game_config.json    <- ALL constants here
+-- assets/
|   +-- data/               <- JSON data (entities, levels, characters)
|   +-- images/
|   +-- sounds/
+-- tests/
|   +-- test_game_state.py
|   +-- test_rules.py
+-- TOOLS/
|   +-- build_web_mobile.py <- portrait/mobile web build script (the only web build)
+-- WEB_BUILD/
    +-- index_mobile.html   <- black-background mobile page template
    +-- web_build_notes.md  <- read before touching the template
```

---

## What the AI agent should never do
- Import pygame anywhere in src/game/
- Hardcode a number that belongs in game_config.json
- Use a global variable
- Write a function without type hints
- Leave tests failing

## When asked "what should we do?" / "what's next?" / "pick something"
1. Open `docs/log.md`
2. Open the current plan (`docs/superpowers/plans/<latest>.md`)
3. List the next unchecked tasks (checkbox syntax: `- [ ]`)
4. Offer them as numbered choices — let the user pick or say "all of them"

## After each task completes
- Update the checkbox in the plan (`- [ ]` -> `- [x]`)
- Append a one-line entry to `docs/log.md` under today's session heading
- Commit with a descriptive message

## Authority order (when docs disagree)
1. `docs/schema.md` — game data model intent
2. `src/fanbidextrous/models/` — exact behavior
3. `the_idea.md` — architecture and scope

### Shell environment
- User's shell is **Windows PowerShell 5.1**. The Bash tool runs **git bash** (Unix paths, `source`, `&&` chaining all work there).
- Use the Bash tool for all shell commands — it handles paths and chaining correctly.
- For paths with spaces use double quotes in Bash: `"C:/Users/jamiespa/My Drive/..."`.
- PowerShell 5.1 does NOT support `&&` or `||` pipeline chain operators — never generate raw PowerShell for the user to paste unless you use `;` or `if ($?) {...}` instead.

### Python — always use the venv
- **NEVER use bare `python`** — it hits the MS Store stub and does nothing.
- All Python invocations: `.venv/Scripts/python`
- All pip invocations: `.venv/Scripts/pip`
- All tools (pytest, pygbag): `.venv/Scripts/<tool>`
- Python version is **3.11** (not 3.12). No `uv` installed.
- See `docs/commands.md` for the full command reference.

### PHP sync relay specifics
The two clients do NOT run a Python cache server. Instead, a tiny PHP script on
drpeterjamieson.com acts as a shared bulletin board. Each client independently reads
the same live sports APIs and runs the same deterministic RNG; the only thing that
needs to travel over the wire is each player's pick for the current window.

- PHP relay lives at `php/sync.php` in this repo; deploy to the website via FTP/SFTP.
- Endpoint (read): `GET https://drpeterjamieson.com/game/sync.php?session=SESSION_CODE`
  Returns JSON: `{"window": N, "player_a_pick": "...", "player_b_pick": "...", "rng_seed": S}`
- Endpoint (write): `POST https://drpeterjamieson.com/game/sync.php`
  Body: `{"session": SESSION_CODE, "slot": 0_or_1, "window": N, "pick": "PICK_STRING"}`
- The PHP script appends picks to a flat JSON file per session on the server filesystem.
  No database required -- session files are small and short-lived.
- SESSION_CODE is a short random string (e.g. "X7K2") generated by Player A and shared
  with Player B out-of-band (text message, voice). Both clients enter it on the join screen.
- RNG_SEED is set ONCE per session by Player A's client on session creation and written to
  the sync file. Player B reads it on join. Both clients call `random.seed(RNG_SEED)` before
  any randomized game logic. After that, both clients advance the RNG identically as long
  as they process the same events in the same order -- which they will, because they both
  read the same sports API data.
- Sports API calls (NHL play-by-play, Balldontlie events) are made directly by each client
  independently. Both clients poll on the same 120-second wall-clock rhythm anchored to
  the RNG seed timestamp, so they see the same event batches.
- Balldontlie API key is embedded in the pygbag build (client-side). It is the free tier
  key; rate limit exposure is 2 clients x 0.5 req/min = 1 req/min total, within the 5 req/min
  cap. Document this in `docs/api-notes.md`. If key exposure is a concern in v2, proxy it.
- NEVER store sensitive user data in the PHP sync file -- only picks and the seed.

### pygame-ce and pygbag specifics
- The game library is **pygame-ce** (community edition), NOT the original `pygame` package.
  Install: `.venv/Scripts/pip install pygame-ce`
  Import: `import pygame` (same namespace, different package)
- **pygbag** is the HTML/WASM build target.
  Install: `.venv/Scripts/pip install pygbag`
  Run dev server: `.venv/Scripts/python -m pygbag --port 8000 src/`
  Build for web: `.venv/Scripts/python -m pygbag --build src/`
  Output lands in `build/web/`
- pygbag requires the entry point to be `src/main.py` (or a package with `__main__.py`).
- pygbag async loop: the main game loop MUST be an `async def main()` coroutine and call
  `await asyncio.sleep(0)` once per frame so the browser event loop can breathe.
  Non-async code will freeze the browser tab.
- Do NOT use `pygame.mixer` features that rely on file I/O in the pygbag build — use
  `pygame.mixer.Sound` with pre-loaded bytes or omit audio for v1 web build.
- Asset paths: use `pathlib.Path(__file__).parent / "assets"` — never hardcode absolute paths.
  pygbag serves assets relative to the build root; keep all assets inside `src/assets/`.

### ASCII-only rule (CRITICAL)
Windows PowerShell/terminal cannot render non-ASCII characters — they produce `UnicodeEncodeError` or display as `?`/garbage.

**NEVER use these in any Python `print()`, CLI output, log files, or generated text files:**
- Checkmarks / crosses: use `OK` / `FAIL`
- Arrows: use `->` `<-` `==>` `>`
- Box-drawing: use `===` `---` `|`
- Emoji of any kind
- Any character outside ASCII (0x00-0x7F)

This applies to: `print()` statements, `logging`, CLI output, `.md` log files, error messages.
Exception: string literals rendered only inside the pygame surface (not printed) may use Unicode
if the font supports it.
