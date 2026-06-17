# src/main.py
"""Desktop entry point.

Default: the canned MockFeed demo. Pass --sim <slug> to play a recorded real World Cup
match instead, e.g.:
    .venv/Scripts/python src/main.py --sim wc2018_final_fra_cro
"""
import asyncio
import sys
from src.ui.app import App
from src.ui import demo_flow


async def main() -> None:
    app = App()
    if "--sim" in sys.argv:
        slug = sys.argv[sys.argv.index("--sim") + 1]
        demo_flow.start_simulation(app, f"assets/data/simulations/{slug}.json")
    else:
        demo_flow.start(app)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
