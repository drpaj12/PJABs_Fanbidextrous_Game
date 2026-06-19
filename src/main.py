# src/main.py
"""Desktop entry point.

  .venv/Scripts/python src/main.py                      # MockFeed demo (no SIM)
  .venv/Scripts/python src/main.py --simdemo            # MockFeed demo + SIM hotkeys
  .venv/Scripts/python src/main.py --sim <slug>         # recorded match + SIM hotkeys
  .venv/Scripts/python src/main.py --live [fixture_id]  # LIVE match off the relay
"""
import asyncio
import sys
from pathlib import Path

# Allow `python src/main.py` (run by path) to find the `src` package: the project
# root is this file's grandparent. Harmless under `-m src.main` / PYTHONPATH too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui.app import App
from src.ui import flow
from src.utils.constants import CONFIG


async def main() -> None:
    app = App()
    if "--sim" in sys.argv:
        slug = sys.argv[sys.argv.index("--sim") + 1]
        flow.start_simulation(app, f"assets/data/simulations/{slug}.json", sim_mode=True)
    elif "--live" in sys.argv:
        i = sys.argv.index("--live")
        arg = sys.argv[i + 1] if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit() \
            else None
        fixture_id = int(arg) if arg is not None else CONFIG["live"]["fixture_id"]
        if fixture_id is None:
            print("FAIL: no live fixture id. Pass one (--live 12345) or set "
                  "config live.fixture_id once a valid API key is in place.")
            return
        flow.start_live(app, int(fixture_id), sim_mode="--simlive" in sys.argv)
    elif "--simdemo" in sys.argv:
        flow.start(app, sim_mode=True)
    else:
        flow.start(app, sim_mode=False)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
