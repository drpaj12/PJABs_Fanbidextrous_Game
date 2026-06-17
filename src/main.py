# src/main.py
"""Desktop entry point.

  .venv/Scripts/python src/main.py                      # MockFeed demo (no SIM)
  .venv/Scripts/python src/main.py --simdemo            # MockFeed demo + SIM hotkeys
  .venv/Scripts/python src/main.py --sim <slug>         # recorded match + SIM hotkeys
"""
import asyncio
import sys
from src.ui.app import App
from src.ui import flow


async def main() -> None:
    app = App()
    if "--sim" in sys.argv:
        slug = sys.argv[sys.argv.index("--sim") + 1]
        flow.start_simulation(app, f"assets/data/simulations/{slug}.json", sim_mode=True)
    elif "--simdemo" in sys.argv:
        flow.start(app, sim_mode=True)
    else:
        flow.start(app, sim_mode=False)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
