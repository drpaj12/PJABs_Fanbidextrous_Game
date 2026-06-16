# [Your Game Name]

*A DarkWeb GameJam entry -- Meaningful Play 2026*

Replace every line in [brackets] with your own content before you start coding.

---

## What Is This Game?

[Write 2-3 sentences here. What is the game? Who plays it? What is the goal?]

Example: "A game where each player takes turns performing one action that
changes the shared game state. The game continues until a win condition is
met or a turn limit is reached. Whoever has the most points when the game
ends wins."

This description becomes the opening paragraph of your DESIGN.md. Write it
here first in plain language -- you will paste it into a chat with your AI
agent to kick off the whole project.

---

## Step 1 -- Install Python

You need Python 3.10 or higher. Check if you have it:

    python --version

If you see Python 3.10.x or higher, skip to Step 2.

If not, download it from https://www.python.org/downloads/
- Windows: run the installer, check "Add Python to PATH", click Install Now
- Mac: use the macOS installer from python.org, or: brew install python
- Linux: sudo apt install python3 python3-pip python3-venv

After installing, close and reopen your terminal, then verify:

    python --version

---

## Step 2 -- Create a Virtual Environment

A virtual environment keeps this project's dependencies separate from
everything else on your machine. Do this once per project.

Navigate to your project folder (where this README.md lives), then:

    python -m venv .venv

Activate it:

    Windows (Command Prompt):   .venv\Scripts\activate
    Windows (PowerShell):       .venv\Scripts\Activate.ps1
    Mac / Linux:                source .venv/bin/activate

You will see (.venv) at the start of your terminal prompt when it is active.
Always activate the venv before running the game or installing packages.

Install the project dependencies:

    pip install -r requirements.txt

To confirm everything installed:

    pip list

You should see pygame-ce, pygbag, and pytest in the list.

---

## Step 3 -- Set Up Your Coding Environment

Pick one AI coding agent and install it now, before the jam starts.

### Option A: Claude Code (terminal-based)

Install Node.js 18+ from https://nodejs.org
Then:

    npm install -g @anthropic-ai/claude-code

Get an API key at https://console.anthropic.com
Run Claude Code from inside your project folder:

    claude

Claude Code reads CLAUDE.md automatically at the start of every session.
You do not need to re-explain the project each time.

### Option B: VS Code + GitHub Copilot

1. Install VS Code from https://code.visualstudio.com
2. Create a GitHub account at https://github.com
3. Install the "GitHub Copilot" extension inside VS Code
4. Sign in with GitHub -- Copilot activates automatically
5. Open the Copilot chat panel (Ctrl+Shift+I or Cmd+Shift+I)
6. At the start of each session, paste the contents of CLAUDE.md into
   the chat so Copilot knows your project rules

---

## Step 4 -- Run the Game

Make sure your venv is active (you see (.venv) in the prompt), then:

    python src/main.py

The game window opens. Press ENTER on the menu screen and SPACE to take
an action. This is the sample game loop -- replace the logic with yours.

### Run on the Web

For a quick local preview, run pygbag directly against the project root
(it reads `main.py` and `pygbag.ini` automatically):

    pygbag .

Open http://localhost:8000 in a browser. This is how your final submission
will run -- test it in the browser before you submit.

For a real deployable build (desktop/landscape and portrait/mobile, with
the black-background loading screen instead of pygbag's plain default),
use the scripts in `TOOLS/` instead -- see Step 5 below.

### Run the Tests

    python -m pytest tests/

All tests should pass before every session and after every change. If a
test fails, fix it before adding new features.

---

## Step 5 -- How to Use These Files as Samples

Every file in this template is a working example. Do not delete them --
modify them. Here is what each one is for and how to adapt it:

### CLAUDE.md -- your AI agent's rulebook
This is the most important file. It tells the AI agent the rules of your
project. Read it now. Then update these sections to match your game:
- The directory layout (if you add new folders)
- The "What the AI agent should never do" list (add your own rules)
- Any game-specific constraints from your DESIGN.md

### DESIGN.md -- your game design document
Fill in every section before you write any code. The AI reads this to
understand what it is building. The more specific you are, the better
the code. Vague sections produce vague code.

### config/game_config.json -- all your constants
Every number in your game lives here. Colors, screen size, speeds, scores,
health values -- everything. Change a value here and it changes everywhere
in the game. Never hardcode a number in your Python files.

### src/game/game_state.py -- your game's data
The GameState class holds everything that can change during a game: scores,
health, turn number, whose turn it is, what phase the game is in. It works
for any number of players -- pass as many names as your game needs. Replace
the Player fields with whatever your game tracks. Add methods for every
state transition your game needs.

### src/game/rules.py -- your game's logic
apply_action() is where a player action changes the game state. Replace
the stub "place" logic with your real rules. check_winner() is where you
test win/lose conditions after every action. Add one condition per rule
in your DESIGN.md.

### src/game/entities.py -- your game's objects
The Entity and Collection classes are examples. Replace them with whatever
your game uses: cards, tiles, units, dice, resources, locations. Keep all
attributes as plain Python data (int, str, list) -- no pygame, no images here.

### src/ui/game_window.py -- your screen states
The three screen states (menu, playing, game_over) are the minimum every
game needs. Add states for: team select, difficulty, tutorial, settings,
credits. Each state gets its own draw function.

### src/ui/components.py -- reusable widgets
Button, Label, and Panel are ready to use. Copy and modify them for any
UI element your game needs: card display panels, health bars, score boards.

### tests/test_game_state.py -- your automated tests
Add one test every time you add a new rule. Run the tests without a screen
(no pygame needed) so you can catch logic errors fast. Copy the test
structure -- class per module, one test per behavior.

### .gitignore -- what git should not track
Keeps caches, virtual environments, IDE files, and generated web-build
output out of your repo. The one section worth understanding:
`WEB_BUILD/*` ignores everything in that folder *except*
`index_desktop.html`, `index_mobile.html`, and `web_build_notes.md` --
those three are hand-authored templates and documentation, not build
output, so they stay tracked while the generated zips/apk/tar.gz do not.

### main.py (project root) -- the web entry point
pygbag requires a `main.py` at the project root with an async main loop.
This is separate from `src/main.py` (your desktop entry point) but both
call the same `src/ui/game_window.run()` -- there is only one game loop
to maintain. It also wraps the game in a try/except that draws fatal
errors directly onto the canvas, since you cannot open a browser console
on every device you might test on.

### pygbag.ini -- web build settings
Sets the browser tab title, package name, and window dimensions for the
web build. Keep `width`/`height` here in sync with
`config/game_config.json`'s `display.width`/`display.height`.

### TOOLS/build_web.py and TOOLS/build_web_mobile.py -- web build scripts
Run these to produce a deployable zip: `build_web.py` for a desktop/
landscape build, `build_web_mobile.py` for a portrait/mobile build. Both
stage a clean copy of the project, run pygbag, install the black-
background `index_desktop.html`/`index_mobile.html` template over
pygbag's plain default, and zip the result into `WEB_BUILD/`.

### WEB_BUILD/ -- web build templates and docs
`index_desktop.html` and `index_mobile.html` are the hand-crafted page
templates the build scripts install (black background, correct canvas
sizing, cache-busting). `web_build_notes.md` explains why they exist and
how to change canvas dimensions if you resize your game. Read it before
touching either template. Generated zips land here too but are gitignored.

---

## Step 6 -- Using Chat with a GenAI to Build Your Files

The fastest way to start is to have a conversation with your AI agent.
Here is the exact sequence:

### 6a. Start with your game idea (plain language)

Open a chat (Claude Code terminal, or Copilot chat panel) and say:

    I am building a game for the DarkWeb GameJam at Meaningful Play 2026.
    Here is my game idea: [paste your 2-3 sentence description from above].
    Read CLAUDE.md and DESIGN.md. Ask me questions until you understand
    the game well enough to fill in every section of DESIGN.md.

Let the AI ask questions. Answer them. When it has enough, say:

    Now write a completed DESIGN.md based on our conversation.

Review what it writes. Correct anything that does not match your intent.
This is your design document -- own it.

### 6b. Update CLAUDE.md for your game

Once DESIGN.md is filled in, say:

    Read DESIGN.md. Update CLAUDE.md so it accurately describes this
    specific game: the entities, the rules, the turn structure, and any
    constraints that are unique to this project.

This personalizes the AI agent's rulebook to your game.

### 6c. Update game_config.json

Say:

    Read DESIGN.md. Update config/game_config.json with the right
    starting values for this game: health, score limits, turn count,
    number of players, entity counts, and any other constants the
    game needs. Add a comment for each new key.

### 6d. Build one module at a time

Start with game_state.py:

    Read DESIGN.md section 8 (Game State). Rewrite src/game/game_state.py
    so GameState tracks exactly the data listed there. Keep the existing
    style: dataclass for Player, constructor for GameState, no pygame.

Then rules.py:

    Read DESIGN.md sections 5 and 6 (Turn Structure, Win Conditions).
    Rewrite src/game/rules.py so apply_action() handles one real turn
    from my game and check_winner() tests all win conditions.

Then tests:

    Write tests in tests/test_game_state.py that verify every rule
    you just implemented. Run them and confirm they all pass.

Then the UI:

    Read src/game/game_state.py and src/game/rules.py.
    Update src/ui/game_window.py so the playing state calls the real
    game logic. Add one screen state at a time -- do not build
    the whole UI in one pass.

### 6e. The rule: one module, then test, then move on

After every module the AI builds, run:

    python -m pytest tests/
    python src/main.py

If tests fail or the game does not launch, fix it before continuing.
Tell the AI what broke and let it fix it. Never stack two broken modules.

---

## How to Play

[Fill this in once the game is playable.]

Describe:
- Controls (what keys or mouse actions does the player use?)
- Objective (what is the player trying to do?)
- One complete turn (walk through it step by step)

---

## Team

- [Name], [role]
- [Name], [role]

---

## AI Agent Used

- [ ] Claude Code
- [ ] VS Code + GitHub Copilot

---

## Project Structure

```
your-game/
+-- CLAUDE.md            AI agent rulebook (read this first)
+-- DESIGN.md            Game design document (fill in before coding)
+-- README.md            This file
+-- requirements.txt     pip dependencies
+-- log.md               One-line changelog per session
+-- .gitignore           What git should not track
+-- main.py              Web entry point (pygbag reads this)
+-- pygbag.ini           Web build title/package/dimensions
+-- src/
|   +-- main.py          Desktop entry point
|   +-- game/            Pure Python game logic (zero pygame)
|   +-- ui/              All pygame rendering
|   +-- utils/           Config loading and asset management
+-- config/
|   +-- game_config.json All constants (no magic numbers in code)
+-- assets/
|   +-- data/            JSON data files (entities, levels, etc.)
|   +-- images/
|   +-- sounds/
+-- tests/               pytest tests (run without a display)
+-- TOOLS/
|   +-- build_web.py        Desktop/landscape web build script
|   +-- build_web_mobile.py Portrait/mobile web build script
+-- WEB_BUILD/
    +-- index_desktop.html  Black-background desktop page template
    +-- index_mobile.html   Black-background mobile page template
    +-- web_build_notes.md  Why the templates exist, how to resize them
```

---

## License

Built for educational use at Miami University ECE / Meaningful Play 2026.
